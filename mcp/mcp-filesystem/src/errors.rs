use thiserror::Error;
use uuid::Uuid;

#[derive(Debug, Error)]
pub enum FilesystemError {
    #[error("Tenant {0} non autorisé")]
    TenantForbidden(Uuid),

    #[error("Permission insuffisante : {0} requis")]
    PermissionDenied(String),

    #[error("Ressource introuvable : {0}")]
    NotFound(String),

    #[error("Validation échouée : {0}")]
    ValidationError(String),

    #[error("Fichier trop volumineux : {size} chars, max {max} chars")]
    FileTooLarge { size: usize, max: usize },

    #[error("Type MIME non supporté : {0}")]
    UnsupportedMimeType(String),

    #[error("Erreur de stockage : {0}")]
    StorageError(String),

    #[error("Service RAG indisponible")]
    RagServiceUnavailable,

    #[error("Confirmation requise pour cette opération destructrice")]
    ConfirmationRequired,

    #[error("Erreur base de données")]
    DatabaseError(#[from] sqlx::Error),

    #[error("Erreur interne")]
    InternalError(#[from] anyhow::Error),
}

impl FilesystemError {
    pub fn error_code(&self) -> &'static str {
        match self {
            FilesystemError::TenantForbidden(_) => "TENANT_FORBIDDEN",
            FilesystemError::PermissionDenied(_) => "PERMISSION_DENIED",
            FilesystemError::NotFound(_) => "NOT_FOUND",
            FilesystemError::ValidationError(_) => "VALIDATION_ERROR",
            FilesystemError::FileTooLarge { .. } => "FILE_TOO_LARGE",
            FilesystemError::UnsupportedMimeType(_) => "UNSUPPORTED_MIME_TYPE",
            FilesystemError::StorageError(_) => "STORAGE_ERROR",
            FilesystemError::RagServiceUnavailable => "RAG_SERVICE_UNAVAILABLE",
            FilesystemError::ConfirmationRequired => "CONFIRMATION_REQUIRED",
            FilesystemError::DatabaseError(_) => "DATABASE_ERROR",
            FilesystemError::InternalError(_) => "INTERNAL_ERROR",
        }
    }

    pub fn http_status(&self) -> u16 {
        match self {
            FilesystemError::TenantForbidden(_) => 403,
            FilesystemError::PermissionDenied(_) => 403,
            FilesystemError::NotFound(_) => 404,
            FilesystemError::ValidationError(_) => 422,
            FilesystemError::FileTooLarge { .. } => 422,
            FilesystemError::UnsupportedMimeType(_) => 422,
            FilesystemError::StorageError(_) => 500,
            FilesystemError::RagServiceUnavailable => 503,
            FilesystemError::ConfirmationRequired => 409,
            FilesystemError::DatabaseError(_) => 500,
            FilesystemError::InternalError(_) => 500,
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
