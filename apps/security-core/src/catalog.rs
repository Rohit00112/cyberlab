//! Challenge catalog's first PostgreSQL read path.
//!
//! This module intentionally returns only IDs and a total. Flag hashes, hints,
//! draft content and other private fields never leave the database through
//! this endpoint. FastAPI performs authentication and formats challenge data.
use deadpool_postgres::Pool;
use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize)]
pub struct CatalogQuery {
    pub editor: bool,
    pub status: Option<String>,
    pub category: Option<String>,
    pub difficulty: Option<String>,
    pub limit: i64,
    pub offset: i64,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct CatalogPage {
    pub ids: Vec<String>,
    pub total: i64,
}

pub fn validate_query(request: &CatalogQuery) -> Result<(), &'static str> {
    if !(1..=200).contains(&request.limit) || request.offset < 0 {
        return Err("invalid pagination");
    }
    if request
        .status
        .as_ref()
        .is_some_and(|value| value.len() > 16)
        || request
            .category
            .as_ref()
            .is_some_and(|value| value.len() > 32)
        || request
            .difficulty
            .as_ref()
            .is_some_and(|value| value.len() > 16)
    {
        return Err("invalid catalog filter");
    }
    Ok(())
}

#[derive(Debug)]
pub enum CatalogError {
    Invalid,
    Database,
}

pub async fn query_catalog(
    pool: &Pool,
    request: &CatalogQuery,
) -> Result<CatalogPage, CatalogError> {
    validate_query(request).map_err(|_| CatalogError::Invalid)?;
    let mut client = pool.get().await.map_err(|_| CatalogError::Database)?;
    // Two queries share a snapshot. The API may hydrate records later, so
    // it must still enforce visibility when returning the final objects.
    let transaction = client
        .build_transaction()
        .read_only(true)
        .isolation_level(tokio_postgres::IsolationLevel::RepeatableRead)
        .start()
        .await
        .map_err(|_| CatalogError::Database)?;

    // For non-editors, ignore any supplied status filter entirely: only
    // published challenges can be returned, even on forged internal inputs.
    let status = if request.editor {
        request.status.as_deref().filter(|s| !s.is_empty())
    } else {
        None
    };
    let category = request.category.as_deref().filter(|s| !s.is_empty());
    let difficulty = request.difficulty.as_deref().filter(|s| !s.is_empty());
    let filters = "
        FROM challenges
        WHERE ($1::boolean OR status = 'published')
          AND ($2::text IS NULL OR status = $2)
          AND ($3::text IS NULL OR category = $3)
          AND ($4::text IS NULL OR difficulty = $4)";
    let total: i64 = transaction
        .query_one(
            &format!("SELECT count(*) {filters}"),
            &[&request.editor, &status, &category, &difficulty],
        )
        .await
        .map_err(|_| CatalogError::Database)?
        .get(0);
    let rows = transaction
        .query(
            &format!(
                "SELECT id::text {filters} ORDER BY points DESC, created_at DESC, id ASC LIMIT $5 OFFSET $6"
            ),
            &[
                &request.editor,
                &status,
                &category,
                &difficulty,
                &request.limit,
                &request.offset,
            ],
        )
        .await
        .map_err(|_| CatalogError::Database)?;
    transaction
        .commit()
        .await
        .map_err(|_| CatalogError::Database)?;
    Ok(CatalogPage {
        ids: rows.into_iter().map(|row| row.get(0)).collect(),
        total,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid() -> CatalogQuery {
        CatalogQuery {
            editor: false,
            status: Some("draft".into()),
            category: None,
            difficulty: None,
            limit: 100,
            offset: 0,
        }
    }

    #[test]
    fn pagination_is_bounded() {
        let mut request = valid();
        assert!(validate_query(&request).is_ok());
        request.limit = 0;
        assert!(validate_query(&request).is_err());
        request.limit = 201;
        assert!(validate_query(&request).is_err());
        request.limit = 1;
        request.offset = -1;
        assert!(validate_query(&request).is_err());
    }

    #[test]
    fn oversized_filters_rejected() {
        let mut request = valid();
        request.category = Some("c".repeat(33));
        assert!(validate_query(&request).is_err());
    }
}
