use thiserror::Error;
use uuid::Uuid;

#[derive(Debug, Error)]
pub enum BillingError {
    #[error("Tenant {0} non autorisé")]
    TenantForbidden(Uuid),

    #[error("Permission insuffisante : {0} requis")]
    PermissionDenied(String),

    #[error("Ressource introuvable : {0}")]
    NotFound(String),

    #[error("Validation échouée : {0}")]
    ValidationError(String),

    #[error("Transition invalide : {from} → {to}")]
    InvalidTransition { from: String, to: String },

    #[error("Aucun abonnement actif pour ce tenant")]
    NoActiveSubscription,

    #[error("Erreur base de données")]
    DatabaseError(#[from] sqlx::Error),

    #[error("Erreur interne")]
    InternalError(#[from] anyhow::Error),
}

impl BillingError {
    pub fn error_code(&self) -> &'static str {
        match self {
            BillingError::TenantForbidden(_) => "TENANT_FORBIDDEN",
            BillingError::PermissionDenied(_) => "PERMISSION_DENIED",
            BillingError::NotFound(_) => "NOT_FOUND",
            BillingError::ValidationError(_) => "VALIDATION_ERROR",
            BillingError::InvalidTransition { .. } => "INVALID_TRANSITION",
            BillingError::NoActiveSubscription => "NO_ACTIVE_SUBSCRIPTION",
            BillingError::DatabaseError(_) => "DATABASE_ERROR",
            BillingError::InternalError(_) => "INTERNAL_ERROR",
        }
    }

    pub fn http_status(&self) -> u16 {
        match self {
            BillingError::TenantForbidden(_) => 403,
            BillingError::PermissionDenied(_) => 403,
            BillingError::NotFound(_) => 404,
            BillingError::ValidationError(_) => 422,
            BillingError::InvalidTransition { .. } => 422,
            BillingError::NoActiveSubscription => 404,
            BillingError::DatabaseError(_) => 500,
            BillingError::InternalError(_) => 500,
        }
    }

    pub fn to_mcp_error_content(&self) -> serde_json::Value {
        serde_json::json!({
            "error": self.error_code(),
            "message": self.to_string(),
            "status": self.http_status(),
        })
    }
}
