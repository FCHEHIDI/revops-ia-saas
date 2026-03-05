use async_trait::async_trait;
use std::path::PathBuf;
use tokio::fs;
use tracing::instrument;

use crate::errors::FilesystemError;

// ---------------------------------------------------------------------------
// ObjectStorage trait
// ---------------------------------------------------------------------------

#[async_trait]
pub trait ObjectStorage: Send + Sync {
    /// Reads the raw bytes of a stored object.
    async fn read_content(&self, path: &str) -> Result<Vec<u8>, FilesystemError>;

    /// Writes raw bytes to the given path, creating intermediate directories as needed.
    async fn write(&self, path: &str, content: &[u8]) -> Result<(), FilesystemError>;

    /// Deletes the object at the given path.
    /// Returns the number of bytes freed.
    async fn delete(&self, path: &str) -> Result<u64, FilesystemError>;

    /// Returns true if the object exists.
    async fn exists(&self, path: &str) -> Result<bool, FilesystemError>;
}

// ---------------------------------------------------------------------------
// LocalStorage — MVP implementation using tokio::fs
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct LocalStorage {
    pub base_dir: PathBuf,
}

impl LocalStorage {
    pub fn new(base_dir: impl Into<PathBuf>) -> Self {
        LocalStorage {
            base_dir: base_dir.into(),
        }
    }

    fn resolve(&self, path: &str) -> PathBuf {
        // Prevent path traversal: strip leading `/` so it is always relative to base_dir
        let sanitized = path.trim_start_matches('/');
        self.base_dir.join(sanitized)
    }
}

#[async_trait]
impl ObjectStorage for LocalStorage {
    #[instrument(skip(self), fields(path = %path))]
    async fn read_content(&self, path: &str) -> Result<Vec<u8>, FilesystemError> {
        let full_path = self.resolve(path);
        fs::read(&full_path).await.map_err(|e| {
            FilesystemError::StorageError(format!(
                "Failed to read '{}': {}",
                full_path.display(),
                e
            ))
        })
    }

    #[instrument(skip(self, content), fields(path = %path, bytes = content.len()))]
    async fn write(&self, path: &str, content: &[u8]) -> Result<(), FilesystemError> {
        let full_path = self.resolve(path);

        if let Some(parent) = full_path.parent() {
            fs::create_dir_all(parent).await.map_err(|e| {
                FilesystemError::StorageError(format!(
                    "Failed to create directories for '{}': {}",
                    parent.display(),
                    e
                ))
            })?;
        }

        fs::write(&full_path, content).await.map_err(|e| {
            FilesystemError::StorageError(format!(
                "Failed to write '{}': {}",
                full_path.display(),
                e
            ))
        })
    }

    #[instrument(skip(self), fields(path = %path))]
    async fn delete(&self, path: &str) -> Result<u64, FilesystemError> {
        let full_path = self.resolve(path);

        let metadata = fs::metadata(&full_path).await.map_err(|e| {
            FilesystemError::StorageError(format!(
                "Failed to stat '{}': {}",
                full_path.display(),
                e
            ))
        })?;
        let size = metadata.len();

        fs::remove_file(&full_path).await.map_err(|e| {
            FilesystemError::StorageError(format!(
                "Failed to delete '{}': {}",
                full_path.display(),
                e
            ))
        })?;

        Ok(size)
    }

    #[instrument(skip(self), fields(path = %path))]
    async fn exists(&self, path: &str) -> Result<bool, FilesystemError> {
        let full_path = self.resolve(path);
        Ok(full_path.exists())
    }
}
