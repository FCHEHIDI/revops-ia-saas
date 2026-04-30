use thiserror::Error;
use uuid::Uuid;

#[derive(Debug, Error)]
pub enum CrmError {
    #[error("Tenant {0} non autorisé")]
    TenantForbidden(Uuid),

    #[error("Permission insuffisante : {0} requis")]
    PermissionDenied(String),

    #[error("Ressource introuvable : {0}")]
    NotFound(String),

    #[error("Validation échouée : {0}")]
    ValidationError(String),

    #[error("Conflit : {0}")]
    ConflictError(String),

    #[error("Transition invalide : {from:?} → {to:?}")]
    InvalidTransition { from: String, to: String },

    #[error("Erreur base de données")]
    DatabaseError(#[from] sqlx::Error),

    #[error("Erreur interne")]
    InternalError(#[from] anyhow::Error),
}

impl CrmError {
    pub fn error_code(&self) -> &'static str {
        match self {
            CrmError::TenantForbidden(_) => "TENANT_FORBIDDEN",
            CrmError::PermissionDenied(_) => "PERMISSION_DENIED",
            CrmError::NotFound(_) => "NOT_FOUND",
            CrmError::ValidationError(_) => "VALIDATION_ERROR",
            CrmError::ConflictError(_) => "CONFLICT",
            CrmError::InvalidTransition { .. } => "INVALID_TRANSITION",
            CrmError::DatabaseError(_) => "DATABASE_ERROR",
            CrmError::InternalError(_) => "INTERNAL_ERROR",
        }
    }

    pub fn http_status(&self) -> u16 {
        match self {
            CrmError::TenantForbidden(_) => 403,
            CrmError::PermissionDenied(_) => 403,
            CrmError::NotFound(_) => 404,
            CrmError::ValidationError(_) => 422,
            CrmError::ConflictError(_) => 409,
            CrmError::InvalidTransition { .. } => 422,
            CrmError::DatabaseError(_) => 500,
            CrmError::InternalError(_) => 500,
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
