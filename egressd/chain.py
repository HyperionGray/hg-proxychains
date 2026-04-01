from typing import Any, Dict, List


def build_relay_string(chain_cfg: Dict[str, Any]) -> str:
    """Build pproxy relay string from chain configuration.
    
    Args:
        chain_cfg: Chain configuration dictionary containing 'hops' list
        
    Returns:
        Relay string with hops joined by '__'
        
    Raises:
        ValueError: If chain.hops is empty or hops are missing URLs
    """
    hops: List[Any] = chain_cfg.get("hops", [])
    if not hops:
        raise ValueError("chain.hops is empty")
    for idx, hop in enumerate(hops):
        if not isinstance(hop, dict) or "url" not in hop:
            raise ValueError(f"chain.hops[{idx}] is missing url")
    return "__".join(hop["url"] for hop in hops)
