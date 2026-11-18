//! H16 laboratory contracts. No CEF, libobs, Production, device or browser launch.
#![forbid(unsafe_code)]

pub type Result<T> = std::result::Result<T, &'static str>;

#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub struct Identity {
    pub instance: u64,
    pub generation: u64,
}
impl Identity {
    pub fn new(instance: u64, generation: u64) -> Result<Self> {
        if instance == 0 || generation == 0 {
            return Err("IDENTITY");
        }
        Ok(Self {
            instance,
            generation,
        })
    }
}

pub mod frame;
pub mod ipc;
pub mod lifecycle;
