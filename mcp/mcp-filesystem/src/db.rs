use anyhow::Result;
use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use uuid::Uuid;

use crate::errors::FilesystemError;

pub async fn create_pool(database_url: &str) -> Result<PgPool> {
    let pool = PgPoolOptions::new()
        .max_connections(20)
        .min_connections(2)
        .acquire_timeout(std::time::Duration::from_secs(5))
        .connect(database_url)
        .await?;
    Ok(pool)
}

/// Validates that a tenant exists and is active, then sets the RLS context.
/// Returns TenantForbidden (403) if the tenant does not exist or is inactive.
/// Sets `app.current_tenant_id` for Row-Level Security enforcement.
pub async fn validate_tenant(tenant_id: Uuid, pool: &PgPool) -> Result<(), FilesystemError> {
    let exists: bool = sqlx::query_scalar(
        "SELECT EXISTS(SELECT 1 FROM organizations WHERE id = $1 AND active = true)",
    )
    .bind(tenant_id)
    .fetch_one(pool)
    .await
    .map_err(FilesystemError::DatabaseError)?;

    if !exists {
        return Err(FilesystemError::TenantForbidden(tenant_id));
    }

    sqlx::query("SELECT set_config('app.current_tenant_id', $1, true)")
        .bind(tenant_id.to_string())
        .execute(pool)
        .await
        .map_err(FilesystemError::DatabaseError)?;

    Ok(())
}
