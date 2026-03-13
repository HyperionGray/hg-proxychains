from typing import Dict, List


def build_relay_string(chain_cfg: Dict) -> str:
    hops: List[Dict] = chain_cfg.get("hops", [])
    if not hops:
        raise ValueError("chain.hops is empty")
    return "__".join(hop["url"] for hop in hops)
