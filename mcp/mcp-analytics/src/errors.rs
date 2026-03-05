use thiserror::Error;
use uuid::Uuid;

#[derive(Debug, Error)]
pub enum AnalyticsError {
    #[error("Tenant {0} non autorisé")]
    TenantForbidden(Uuid),

    #[error("Permission insuffisante : {0} requis")]
    PermissionDenied(String),

    #[error("Validation échouée : {0}")]
    ValidationError(String),

    #[error("Ressource introuvable : {0}")]
    NotFound(String),

    #[error("Erreur base de données")]
    DatabaseError(#[from] sqlx::Error),

    #[error("Erreur interne")]
    InternalError(#[from] anyhow::Error),
}

impl AnalyticsError {
    pub fn error_code(&self) -> &'static str {
        match self {
            AnalyticsError::TenantForbidden(_) => "TENANT_FORBIDDEN",
            AnalyticsError::PermissionDenied(_) => "PERMISSION_DENIED",
            AnalyticsError::ValidationError(_) => "VALIDATION_ERROR",
            AnalyticsError::NotFound(_) => "NOT_FOUND",
            AnalyticsError::DatabaseError(_) => "DATABASE_ERROR",
            AnalyticsError::InternalError(_) => "INTERNAL_ERROR",
        }
    }

    pub fn http_status(&self) -> u16 {
        match self {
            AnalyticsError::TenantForbidden(_) => 403,
            AnalyticsError::PermissionDenied(_) => 403,
            AnalyticsError::ValidationError(_) => 422,
            AnalyticsError::NotFound(_) => 404,
            AnalyticsError::DatabaseError(_) => 500,
            AnalyticsError::InternalError(_) => 500,
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
