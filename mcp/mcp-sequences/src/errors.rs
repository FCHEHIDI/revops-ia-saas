use thiserror::Error;
use uuid::Uuid;

#[derive(Debug, Error)]
pub enum SequencesError {
    #[error("Tenant {0} non autorisé")]
    TenantForbidden(Uuid),

    #[error("Permission insuffisante : {0} requis")]
    PermissionDenied(String),

    #[error("Ressource introuvable : {0}")]
    NotFound(String),

    #[error("Validation échouée : {0}")]
    ValidationError(String),

    #[error("La séquence a {count} enrollments actifs")]
    SequenceHasActiveEnrollments { count: i64 },

    #[error("Contact déjà enrôlé dans cette séquence (enrollment_id: {enrollment_id})")]
    AlreadyEnrolled { enrollment_id: Uuid },

    #[error("La séquence n'est pas active (status requis: active)")]
    SequenceNotActive,

    #[error("Contact {0} introuvable")]
    ContactNotFound(Uuid),

    #[error("Erreur base de données")]
    DatabaseError(#[from] sqlx::Error),

    #[error("Erreur interne")]
    InternalError(#[from] anyhow::Error),
}

impl SequencesError {
    pub fn error_code(&self) -> &'static str {
        match self {
            SequencesError::TenantForbidden(_) => "TENANT_FORBIDDEN",
            SequencesError::PermissionDenied(_) => "PERMISSION_DENIED",
            SequencesError::NotFound(_) => "NOT_FOUND",
            SequencesError::ValidationError(_) => "VALIDATION_ERROR",
            SequencesError::SequenceHasActiveEnrollments { .. } => "SEQUENCE_HAS_ACTIVE_ENROLLMENTS",
            SequencesError::AlreadyEnrolled { .. } => "ALREADY_ENROLLED",
            SequencesError::SequenceNotActive => "SEQUENCE_NOT_ACTIVE",
            SequencesError::ContactNotFound(_) => "CONTACT_NOT_FOUND",
            SequencesError::DatabaseError(_) => "DATABASE_ERROR",
            SequencesError::InternalError(_) => "INTERNAL_ERROR",
        }
    }

    pub fn http_status(&self) -> u16 {
        match self {
            SequencesError::TenantForbidden(_) => 403,
            SequencesError::PermissionDenied(_) => 403,
            SequencesError::NotFound(_) => 404,
            SequencesError::ValidationError(_) => 422,
            SequencesError::SequenceHasActiveEnrollments { .. } => 409,
            SequencesError::AlreadyEnrolled { .. } => 409,
            SequencesError::SequenceNotActive => 422,
            SequencesError::ContactNotFound(_) => 404,
            SequencesError::DatabaseError(_) => 500,
            SequencesError::InternalError(_) => 500,
        }
    }

    pub fn to_mcp_error_content(&self) -> serde_json::Value {
        let mut body = serde_json::json!({
            "error": self.error_code(),
            "message": self.to_string(),
            "status": self.http_status(),
        });

        match self {
            SequencesError::SequenceHasActiveEnrollments { count } => {
                body["active_enrollments"] = serde_json::json!(count);
            }
            SequencesError::AlreadyEnrolled { enrollment_id } => {
                body["enrollment_id"] = serde_json::json!(enrollment_id);
            }
            _ => {}
        }

        body
    }
}
