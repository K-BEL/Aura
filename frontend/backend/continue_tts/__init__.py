"""Continue-1-OSS Text-to-Speech System by SVECTOR."""

__version__ = "1.0.0"

# Only expose the decoder (no vLLM dependency needed)
from .decoder import tokens_decoder_sync
