use anyhow::Result;
use async_trait::async_trait;
use uuid::Uuid;

use crate::models::{
    FinishReason, FunctionCall, LlmResponse, Message, Role, Tool, ToolCall, UsageStats,
};

use super::LlmProvider;

// ---------------------------------------------------------------------------
// Tool-result rendering
// ---------------------------------------------------------------------------

/// Reads the actual MCP tool result payloads from the message history and
/// produces a natural-language reply that surfaces the real data.
///
/// Falls back to the hardcoded synthesis only when no tool result can be parsed.
fn render_tool_results(messages: &[Message], intents: &[&str]) -> String {
    // Collect all tool-result messages in order
    let results: Vec<&str> = messages
        .iter()
        .filter(|m| m.role == Role::Tool)
        .filter_map(|m| m.content.as_deref())
        .collect();

    if results.is_empty() {
        return synthesis_for_intents(intents);
    }

    let mut parts: Vec<String> = Vec::new();

    for raw in &results {
        let Ok(v) = serde_json::from_str::<serde_json::Value>(raw) else {
            continue;
        };

        // ── CRM contacts ────────────────────────────────────────────────
        if let Some(items) = v.get("items").and_then(|i| i.as_array()) {
            let total = v
                .get("total")
                .and_then(|t| t.as_u64())
                .unwrap_or(items.len() as u64);
            let truncated = v.get("_truncated").is_some();

            let mut block = format!("**{} contacts trouvés.**\n\n", total);

            for (i, contact) in items.iter().enumerate() {
                let name = contact
                    .get("full_name")
                    .or_else(|| contact.get("name"))
                    .and_then(|v| v.as_str())
                    .unwrap_or("—");
                let email = contact
                    .get("email")
                    .and_then(|v| v.as_str())
                    .unwrap_or("—");
                let company = contact
                    .get("company")
                    .or_else(|| contact.get("account_name"))
                    .and_then(|v| v.as_str())
                    .unwrap_or("—");
                let status = contact
                    .get("status")
                    .or_else(|| contact.get("lifecycle_stage"))
                    .and_then(|v| v.as_str())
                    .unwrap_or("—");

                block.push_str(&format!(
                    "{}. **{}** · {} · {} · `{}`\n",
                    i + 1,
                    name,
                    email,
                    company,
                    status
                ));
            }

            if truncated {
                block.push_str(&format!(
                    "\n*Affichage des 5 premiers sur {} — précisez un filtre (statut, société…) pour affiner.*",
                    total
                ));
            }

            parts.push(block);
            continue;
        }

        // ── Billing: overdue payments ────────────────────────────────────
        if let Some(overdue) = v.get("overdue_payments").and_then(|i| i.as_array()) {
            let total_amount: f64 = overdue
                .iter()
                .filter_map(|p| p.get("amount").and_then(|a| a.as_f64()))
                .sum();
            let block = format!(
                "**{} paiements en retard** pour un total de **{:.2} €**.\n",
                overdue.len(),
                total_amount
            );
            parts.push(block);
            continue;
        }

        // ── Analytics: MRR trend ─────────────────────────────────────────
        if let Some(points) = v.get("data_points").and_then(|i| i.as_array()) {
            let last = points.last().and_then(|p| p.get("mrr")).and_then(|m| m.as_f64());
            let block = if let Some(mrr) = last {
                format!("**MRR actuel : {:.0} €** ({} points de données).\n", mrr, points.len())
            } else {
                format!("Tendance MRR : {} points de données disponibles.\n", points.len())
            };
            parts.push(block);
            continue;
        }

        // ── Sequences ────────────────────────────────────────────────────
        if let Some(seqs) = v.get("sequences").and_then(|i| i.as_array()) {
            let active: Vec<&str> = seqs
                .iter()
                .filter(|s| s.get("status").and_then(|v| v.as_str()) == Some("active"))
                .filter_map(|s| s.get("name").and_then(|v| v.as_str()))
                .collect();
            let block = format!(
                "**{} séquences actives** : {}.\n",
                active.len(),
                if active.is_empty() {
                    "aucune".to_string()
                } else {
                    active.join(", ")
                }
            );
            parts.push(block);
            continue;
        }

        // ── Fallback: pretty-print unknown structure ─────────────────────
        if let Ok(pretty) = serde_json::to_string_pretty(&v) {
            parts.push(format!("```json\n{}\n```", &pretty[..pretty.len().min(800)]));
        }
    }

    if parts.is_empty() {
        synthesis_for_intents(intents)
    } else {
        parts.join("\n\n")
    }
}

/// Keyword-aware mock LLM provider for E2E tests and `LLM_MOCK=true` dev mode.
///
/// Routes to different MCP tools based on keywords found in the user's last message.
/// The final turn reads the actual tool result payloads and surfaces the real data.
pub struct MockProvider;

// ---------------------------------------------------------------------------
// Intent classification
// ---------------------------------------------------------------------------

/// Classifies keywords in the user message into an ordered list of MCP service intents.
/// Order = priority (first intent = first tool called).
fn classify_intents(text: &str) -> Vec<&'static str> {
    let t = text.to_lowercase();
    let mut intents: Vec<&'static str> = Vec::new();

    if t.contains("contact")
        || t.contains(" crm")
        || t.contains("deal")
        || t.contains("pipeline")
        || t.contains("prospect")
        || t.contains("lead")
        || t.contains("compte client")
    {
        intents.push("crm");
    }

    if t.contains("factur")
        || t.contains("paiement")
        || t.contains("billing")
        || t.contains("impay")
        || t.contains("retard")
        || t.contains("invoice")
        || t.contains("subscription")
        || t.contains("abonnement")
    {
        intents.push("billing");
    }

    if t.contains("mrr")
        || t.contains("analyti")
        || t.contains("tendance")
        || t.contains("croissance")
        || t.contains("conversion")
        || t.contains("churn")
        || t.contains("funnel")
        || t.contains("entonnoir")
        || t.contains("taux")
        || t.contains("kpi")
        || t.contains("métrique")
    {
        intents.push("analytics");
    }

    if t.contains("séquence")
        || t.contains("sequence")
        || t.contains("relance")
        || t.contains("outreach")
        || t.contains("campagne automatis")
        || t.contains("automatisation")
        || t.contains("automation")
    {
        intents.push("sequences");
    }

    // Default: billing
    if intents.is_empty() {
        intents.push("billing");
    }

    intents
}

// ---------------------------------------------------------------------------
// Tool call factory
// ---------------------------------------------------------------------------

fn tool_call_for_intent(intent: &str, tenant_id: &str) -> ToolCall {
    let (name, arguments) = match intent {
        "crm" => (
            "mcp_crm__search_contacts",
            format!(
                r#"{{"tenant_id": "{}", "page": 1, "limit": 10}}"#,
                tenant_id
            ),
        ),
        "analytics" => (
            "mcp_analytics__get_mrr_trend",
            format!(r#"{{"tenant_id": "{}", "months": 3}}"#, tenant_id),
        ),
        "sequences" => (
            "mcp_sequences__list_sequences",
            format!(
                r#"{{"tenant_id": "{}", "page": 1, "limit": 10}}"#,
                tenant_id
            ),
        ),
        // billing (default)
        _ => (
            "mcp_billing__list_overdue_payments",
            format!(r#"{{"tenant_id": "{}"}}"#, tenant_id),
        ),
    };

    ToolCall {
        id: Uuid::new_v4().to_string(),
        call_type: "function".to_string(),
        function: FunctionCall {
            name: name.to_string(),
            arguments,
        },
    }
}

// ---------------------------------------------------------------------------
// Synthesis
// ---------------------------------------------------------------------------

fn synthesis_for_intents(intents: &[&str]) -> String {
    let has = |s: &str| intents.contains(&s);

    if has("crm") && has("billing") {
        "Synthèse RevOps : j'ai analysé les contacts CRM et les paiements en retard. \
         Plusieurs comptes actifs présentent des factures impayées — une relance ciblée \
         sur ces comptes est recommandée pour sécuriser le MRR."
            .to_string()
    } else if has("billing") && has("analytics") {
        "Synthèse RevOps : les paiements en retard (billing) et la tendance MRR (analytics) \
         ont été consultés. La croissance MRR reste solide sur 3 mois ; les factures impayées \
         représentent un risque modéré sur le NRR si elles ne sont pas relancées cette semaine."
            .to_string()
    } else if has("crm") && has("analytics") {
        "Synthèse RevOps : j'ai croisé les données CRM et les métriques analytics. \
         Le pipeline affiche une bonne vélocité. Le taux de conversion lead→client \
         pourrait être amélioré via une séquence onboarding plus agressive."
            .to_string()
    } else if has("analytics") {
        "Synthèse Analytics : la tendance MRR sur 3 mois montre une croissance régulière. \
         Le taux de churn reste maîtrisé. Les métriques de conversion indiquent un pipeline \
         sain — aucune action urgente identifiée."
            .to_string()
    } else if has("crm") {
        "Synthèse CRM : plusieurs leads qualifiés n'ont pas été contactés depuis plus de \
         14 jours. Je recommande de les inscrire dans une séquence de relance automatisée \
         pour maintenir la pression commerciale."
            .to_string()
    } else if has("sequences") {
        "Synthèse Séquences : les séquences actives affichent un bon taux d'engagement. \
         La séquence 'Onboarding SaaS Enterprise' est particulièrement performante. \
         Pensez à réactiver 'Cold Outreach Fintech Q2' mise en pause depuis 10 jours."
            .to_string()
    } else {
        // billing default
        "Synthèse Billing : j'ai consulté les paiements en retard. Plusieurs factures \
         dépassent l'échéance de 30 jours — une relance immédiate est conseillée pour \
         préserver le cash-flow et éviter un impact sur le MRR net."
            .to_string()
    }
}

// ---------------------------------------------------------------------------
// LlmProvider implementation
// ---------------------------------------------------------------------------

#[async_trait]
impl LlmProvider for MockProvider {
    async fn complete(&self, messages: &[Message], _tools: &[Tool]) -> Result<LlmResponse> {
        // Count tool results already accumulated in the conversation
        let tool_result_count = messages.iter().filter(|m| m.tool_call_id.is_some()).count();

        // Extract tenant_id from the system message (first UUID-shaped token on a "tenant" line)
        let tenant_id = messages
            .iter()
            .find(|m| m.role == Role::System)
            .and_then(|m| {
                m.content.as_deref().and_then(|c| {
                    c.lines()
                        .find(|l| l.to_lowercase().contains("tenant"))
                        .and_then(|l| {
                            l.split_whitespace()
                                .find(|w| w.len() == 36 && w.contains('-'))
                                .map(str::to_string)
                        })
                })
            })
            .unwrap_or_else(|| "00000000-0000-0000-0000-000000000001".to_string());

        // Keyword-classify the user's last message
        let last_user_text = messages
            .iter()
            .filter(|m| m.role == Role::User)
            .next_back()
            .and_then(|m| m.content.as_deref())
            .unwrap_or("");

        let intents = classify_intents(last_user_text);

        match tool_result_count {
            0 => {
                // Turn 1 — primary intent
                Ok(LlmResponse {
                    content: None,
                    tool_calls: vec![tool_call_for_intent(intents[0], &tenant_id)],
                    finish_reason: FinishReason::ToolCalls,
                    usage: UsageStats {
                        prompt_tokens: 80,
                        completion_tokens: 20,
                        total_tokens: 100,
                    },
                })
            }
            1 if intents.len() >= 2 => {
                // Turn 2 — secondary intent (multi-service message)
                Ok(LlmResponse {
                    content: None,
                    tool_calls: vec![tool_call_for_intent(intents[1], &tenant_id)],
                    finish_reason: FinishReason::ToolCalls,
                    usage: UsageStats {
                        prompt_tokens: 120,
                        completion_tokens: 22,
                        total_tokens: 142,
                    },
                })
            }
            _ => {
                // Final turn — render actual tool result data from conversation history
                Ok(LlmResponse {
                    content: Some(render_tool_results(messages, &intents)),
                    tool_calls: vec![],
                    finish_reason: FinishReason::Stop,
                    usage: UsageStats {
                        prompt_tokens: 200,
                        completion_tokens: 48,
                        total_tokens: 248,
                    },
                })
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::Role;

    // ── classify_intents ──────────────────────────────────────────────────

    #[test]
    fn classify_billing_keywords() {
        let cases = [
            "montre moi les factures impayées",
            "paiements en retard ce mois",
            "billing summary",
            "invoice overdue",
            "abonnement en cours",
            "subscription status",
        ];
        for msg in &cases {
            let intents = classify_intents(msg);
            assert!(
                intents.contains(&"billing"),
                "Expected 'billing' intent for: {:?}, got {:?}",
                msg,
                intents
            );
        }
    }

    #[test]
    fn classify_analytics_keywords() {
        let cases = [
            "tendance MRR sur 3 mois",
            "analytics revenue",
            "taux de churn du trimestre",
            "funnel de conversion",
            "entonnoir commercial",
            "métriques KPI",
        ];
        for msg in &cases {
            let intents = classify_intents(msg);
            assert!(
                intents.contains(&"analytics"),
                "Expected 'analytics' intent for: {:?}, got {:?}",
                msg,
                intents
            );
        }
    }

    #[test]
    fn classify_sequences_keywords() {
        let cases = [
            "liste des séquences actives",
            "créer une relance outreach",
            "automatisation campagne",
            "automation sequence",
        ];
        for msg in &cases {
            let intents = classify_intents(msg);
            assert!(
                intents.contains(&"sequences"),
                "Expected 'sequences' intent for: {:?}, got {:?}",
                msg,
                intents
            );
        }
    }

    #[test]
    fn classify_multiservice_billing_analytics() {
        let msg = "paiements en retard et tendance mrr du mois dernier";
        let intents = classify_intents(msg);
        assert!(
            intents.contains(&"billing"),
            "Expected 'billing' in intents: {:?}",
            intents
        );
        assert!(
            intents.contains(&"analytics"),
            "Expected 'analytics' in intents: {:?}",
            intents
        );
        // billing must come before analytics (billing keyword matched first)
        let bi = intents.iter().position(|&i| i == "billing").unwrap();
        let ai = intents.iter().position(|&i| i == "analytics").unwrap();
        assert!(bi < ai, "billing should precede analytics in intent order");
    }

    #[test]
    fn classify_crm_billing_combined() {
        let msg = "contacts avec factures impayées";
        let intents = classify_intents(msg);
        assert!(intents.contains(&"crm"), "Expected 'crm'");
        assert!(intents.contains(&"billing"), "Expected 'billing'");
    }

    #[test]
    fn classify_unknown_defaults_to_billing() {
        let msg = "bonjour que puis-je faire pour vous ?";
        let intents = classify_intents(msg);
        // default branch returns ["billing"]
        assert_eq!(intents, vec!["billing"]);
    }

    // ── tool_call_for_intent ──────────────────────────────────────────────

    #[test]
    fn tool_call_billing_is_list_overdue_payments() {
        let tc = tool_call_for_intent("billing", "tenant-abc");
        assert_eq!(tc.function.name, "mcp_billing__list_overdue_payments");
        assert!(tc.function.arguments.contains("tenant-abc"));
    }

    #[test]
    fn tool_call_analytics_is_get_mrr_trend() {
        let tc = tool_call_for_intent("analytics", "tenant-abc");
        assert_eq!(tc.function.name, "mcp_analytics__get_mrr_trend");
        assert!(tc.function.arguments.contains("tenant-abc"));
    }

    #[test]
    fn tool_call_sequences_is_list_sequences() {
        let tc = tool_call_for_intent("sequences", "tenant-abc");
        assert_eq!(tc.function.name, "mcp_sequences__list_sequences");
    }

    #[test]
    fn tool_call_crm_is_search_contacts() {
        let tc = tool_call_for_intent("crm", "tenant-abc");
        assert_eq!(tc.function.name, "mcp_crm__search_contacts");
    }

    // ── MockProvider turns ────────────────────────────────────────────────

    fn system_msg(tenant_id: &str) -> Message {
        Message {
            role: Role::System,
            content: Some(format!("tenant_id: {}", tenant_id)),
            tool_calls: None,
            tool_call_id: None,
            name: None,
        }
    }

    fn user_msg(text: &str) -> Message {
        Message {
            role: Role::User,
            content: Some(text.to_string()),
            tool_calls: None,
            tool_call_id: None,
            name: None,
        }
    }

    fn tool_result_msg(call_id: &str, content: &str) -> Message {
        Message {
            role: Role::Tool,
            content: Some(content.to_string()),
            tool_calls: None,
            tool_call_id: Some(call_id.to_string()),
            name: None,
        }
    }

    #[tokio::test]
    async fn mock_turn_1_billing_returns_overdue_tool_call() {
        let provider = MockProvider;
        let messages = vec![
            system_msg("00000000-0000-0000-0000-000000000001"),
            user_msg("paiements en retard ce mois"),
        ];
        let resp = provider.complete(&messages, &[]).await.unwrap();

        assert_eq!(resp.tool_calls.len(), 1);
        assert_eq!(
            resp.tool_calls[0].function.name,
            "mcp_billing__list_overdue_payments"
        );
        assert!(resp.content.is_none());
    }

    #[tokio::test]
    async fn mock_turn_1_analytics_returns_mrr_tool_call() {
        let provider = MockProvider;
        let messages = vec![
            system_msg("00000000-0000-0000-0000-000000000001"),
            user_msg("tendance mrr sur 6 mois"),
        ];
        let resp = provider.complete(&messages, &[]).await.unwrap();

        assert_eq!(resp.tool_calls.len(), 1);
        assert_eq!(resp.tool_calls[0].function.name, "mcp_analytics__get_mrr_trend");
    }

    #[tokio::test]
    async fn mock_multiservice_billing_analytics_3_turns() {
        let provider = MockProvider;
        let tenant = "00000000-0000-0000-0000-000000000001";

        // Turn 1: no tool results yet → billing tool call
        let messages_t1 = vec![
            system_msg(tenant),
            user_msg("paiements en retard et tendance mrr"),
        ];
        let resp_t1 = provider.complete(&messages_t1, &[]).await.unwrap();
        assert_eq!(resp_t1.tool_calls.len(), 1);
        assert_eq!(
            resp_t1.tool_calls[0].function.name,
            "mcp_billing__list_overdue_payments"
        );

        // Turn 2: 1 tool result → analytics tool call
        let call_id_1 = &resp_t1.tool_calls[0].id;
        let mut messages_t2 = messages_t1.clone();
        messages_t2.push(tool_result_msg(
            call_id_1,
            r#"{"overdue_payments": [{"amount": 1200.0}]}"#,
        ));
        let resp_t2 = provider.complete(&messages_t2, &[]).await.unwrap();
        assert_eq!(resp_t2.tool_calls.len(), 1);
        assert_eq!(
            resp_t2.tool_calls[0].function.name,
            "mcp_analytics__get_mrr_trend"
        );

        // Turn 3: 2 tool results → final text response
        let call_id_2 = &resp_t2.tool_calls[0].id;
        let mut messages_t3 = messages_t2.clone();
        messages_t3.push(tool_result_msg(
            call_id_2,
            r#"{"data_points": [{"period": "2026-03", "mrr": 42000.0}]}"#,
        ));
        let resp_t3 = provider.complete(&messages_t3, &[]).await.unwrap();
        assert!(resp_t3.tool_calls.is_empty(), "Final turn must have no tool calls");
        assert!(
            resp_t3.content.is_some(),
            "Final turn must return text content"
        );
        let text = resp_t3.content.unwrap();
        // render_tool_results should surface the MRR data from turn 2 result
        assert!(
            text.contains("MRR") || text.contains("42000") || text.contains("paiements"),
            "Final response should reference tool results: {:?}",
            text
        );
    }

    #[tokio::test]
    async fn mock_single_service_crm_2_turns() {
        let provider = MockProvider;
        let tenant = "00000000-0000-0000-0000-000000000001";

        // Turn 1 → crm search_contacts
        let messages_t1 = vec![
            system_msg(tenant),
            user_msg("liste des contacts CRM"),
        ];
        let resp_t1 = provider.complete(&messages_t1, &[]).await.unwrap();
        assert_eq!(resp_t1.tool_calls[0].function.name, "mcp_crm__search_contacts");

        // Turn 2: 1 tool result, single intent → final response
        let mut messages_t2 = messages_t1.clone();
        messages_t2.push(tool_result_msg(
            &resp_t1.tool_calls[0].id,
            r#"{"items": [{"full_name": "Alice Martin", "email": "alice@acme.io", "company": "Acme", "status": "active"}], "total": 1}"#,
        ));
        let resp_t2 = provider.complete(&messages_t2, &[]).await.unwrap();
        assert!(resp_t2.tool_calls.is_empty(), "Should be final turn");
        let text = resp_t2.content.unwrap();
        assert!(
            text.contains("Alice Martin") || text.contains("contact"),
            "Should surface CRM data: {:?}",
            text
        );
    }
}
