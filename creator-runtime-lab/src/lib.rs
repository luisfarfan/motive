//! Isolated, data-only Creator Runtime. No Production, libobs or browser linkage.
pub mod model;
pub mod persistence;
pub mod planner;
pub mod receipts;
pub use motive_show_control::model::Error;

pub(crate) fn check(ok: bool, code: &str, message: &str) -> Result<(), Error> {
    if ok {
        Ok(())
    } else {
        Err(Error::new(code, message))
    }
}
pub fn digest<T: serde::Serialize>(value: &T) -> Result<String, Error> {
    use sha2::{Digest, Sha256};
    let bytes = serde_json::to_vec(value).map_err(|_| Error::new("SERIALIZE", "Invalid data"))?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}
pub fn label(s: &str) -> Result<(), Error> {
    check(
        !s.is_empty()
            && s.len() <= 64
            && s.bytes()
                .all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'_'),
        "IDENTITY",
        "Expected bounded ASCII identity",
    )
}
pub fn hash(s: &str) -> Result<(), Error> {
    check(
        s.len() == 64
            && s.bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c)),
        "HASH",
        "Expected lowercase SHA-256",
    )
}
