use anyhow::Result;
use async_trait::async_trait;
use uuid::Uuid;

use crate::models::{FinishReason, FunctionCall, LlmResponse, Message, Role, Tool, ToolCall, UsageStats};

use super::LlmProvider;

/// Keyword-aware mock LLM provider for E2E tests and `LLM_MOCK=true` dev mode.
///
/// Routes to different MCP tools based on keywords found in the user's last message.
/// Multi-intent messages trigger multi-turn behaviour (one tool call per turn):
///   Turn 1 — calls the primary intent tool
///   Turn 2 — calls the secondary intent tool (if multi-intent message)
///   Turn 3+ — returns a synthesised summary tailored to the detected intents
pub struct MockProvider;

// ---------------------------------------------------------------------------
// Intent classification
// ---------------------------------------------------------------------------

/// Classifies keywords in the user message into an ordered list of MCP service intents.
/// Order = priority (first intent = first tool called).
fn classify_intents(text: &str) -> Vec<&'static str> {
    let t = text.to_lowercase();
    let mut intents: Vec<&'static str> = Vec::new();

    if t.contains("contact") || t.contains(" crm") || t.contains("deal")
        || t.contains("pipeline") || t.contains("prospect") || t.contains("lead")
        || t.contains("compte client")
    {
        intents.push("crm");
    }

    if t.contains("factur") || t.contains("paiement") || t.contains("billing")
        || t.contains("impay") || t.contains("retard") || t.contains("invoice")
        || t.contains("subscription") || t.contains("abonnement")
    {
        intents.push("billing");
    }

    if t.contains("mrr") || t.contains("analyti") || t.contains("tendance")
        || t.contains("croissance") || t.contains("conversion") || t.contains("churn")
        || t.contains("funnel") || t.contains("entonnoir") || t.contains("taux")
        || t.contains("kpi") || t.contains("métrique")
    {
        intents.push("analytics");
    }

    if t.contains("séquence") || t.contains("sequence") || t.contains("relance")
        || t.contains("outreach") || t.contains("campagne automatis")
        || t.contains("automatisation") || t.contains("automation")
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
            "mcp_crm__list_contacts",
            format!(r#"{{"tenant_id": "{}", "page": 1, "limit": 10}}"#, tenant_id),
        ),
        "analytics" => (
            "mcp_analytics__get_mrr_trend",
            format!(r#"{{"tenant_id": "{}", "months": 3}}"#, tenant_id),
        ),
        "sequences" => (
            "mcp_sequences__list_sequences",
            format!(r#"{{"tenant_id": "{}", "page": 1, "limit": 10}}"#, tenant_id),
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
        let tool_result_count = messages
            .iter()
            .filter(|m| m.tool_call_id.is_some())
            .count();

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
            .last()
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
                    usage: UsageStats { prompt_tokens: 80, completion_tokens: 20, total_tokens: 100 },
                })
            }
            1 if intents.len() >= 2 => {
                // Turn 2 — secondary intent (multi-service message)
                Ok(LlmResponse {
                    content: None,
                    tool_calls: vec![tool_call_for_intent(intents[1], &tenant_id)],
                    finish_reason: FinishReason::ToolCalls,
                    usage: UsageStats { prompt_tokens: 120, completion_tokens: 22, total_tokens: 142 },
                })
            }
            _ => {
                // Final turn — synthesise based on detected intents
                Ok(LlmResponse {
                    content: Some(synthesis_for_intents(&intents)),
                    tool_calls: vec![],
                    finish_reason: FinishReason::Stop,
                    usage: UsageStats { prompt_tokens: 200, completion_tokens: 48, total_tokens: 248 },
                })
            }
        }
    }
}
