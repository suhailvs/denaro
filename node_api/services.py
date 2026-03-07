import asyncio
import random
import threading
from itertools import permutations

from core.constants import ENDIAN
from core.helpers import sha256, timestamp
from core.manager import (
    block_to_bytes,
    calculate_difficulty,
    create_block,
    get_transactions_merkle_tree,
    get_transactions_merkle_tree_ordered,
)
from transactions import CoinbaseTransaction, Transaction
from node_api.network import NodeInterface, NodesManager
from node_api import state


async def propagate(path: str, args: dict, ignore_url=None, nodes: list = None):
    self_node = NodeInterface(state.self_url or "")
    ignore_node = NodeInterface(ignore_url or "")
    aws = []
    for node_url in nodes or NodesManager.get_propagate_nodes():
        node_interface = NodeInterface(node_url)
        if node_interface.base_url == self_node.base_url or node_interface.base_url == ignore_node.base_url:
            continue
        aws.append(node_interface.request(path, args, self_node.url))
    if aws:
        await asyncio.gather(*aws, return_exceptions=True)


async def create_blocks(blocks: list):
    _, last_block = await calculate_difficulty()
    last_block["id"] = last_block["id"] if last_block != {} else 0
    last_block["hash"] = last_block["hash"] if "hash" in last_block else (30_06_2005).to_bytes(32, ENDIAN).hex()
    i = last_block["id"] + 1
    for block_info in blocks:
        block = block_info["block"]
        txs_hex = block_info["transactions"]
        txs = [await Transaction.from_hex(tx) for tx in txs_hex]
        for tx in txs:
            if isinstance(tx, CoinbaseTransaction):
                txs.remove(tx)
                break
        hex_txs = [tx.hex() for tx in txs]
        block["merkle_tree"] = (
            get_transactions_merkle_tree(hex_txs)
            if i > 22500
            else get_transactions_merkle_tree_ordered(hex_txs)
        )
        block_content = block.get("content") or block_to_bytes(last_block["hash"], block)

        if i <= 22500 and sha256(block_content) != block["hash"] and i != 17972:
            for ordered_txs in permutations(hex_txs):
                block["merkle_tree"] = get_transactions_merkle_tree_ordered(list(ordered_txs))
                block_content = block_to_bytes(last_block["hash"], block)
                if sha256(block_content) == block["hash"]:
                    break
        elif 131309 < i < 150000 and sha256(block_content) != block["hash"]:
            for diff in range(0, 100):
                block["difficulty"] = diff / 10
                block_content = block_to_bytes(last_block["hash"], block)
                if sha256(block_content) == block["hash"]:
                    break

        assert i == block["id"]
        if not await create_block(
            block_content.hex() if isinstance(block_content, bytes) else block_content,
            txs,
            last_block,
        ):
            return False
        last_block = block
        i += 1
    return True


async def _sync_blockchain(node_url: str = None):
    db = state.get_db()
    if not node_url:
        nodes = NodesManager.get_recent_nodes()
        if not nodes:
            return
        node_url = random.choice(nodes)
    node_url = node_url.strip("/")
    _, last_block = await calculate_difficulty()
    starting_from = await db.get_next_block_id()
    node_interface = NodeInterface(node_url)
    local_cache = None
    if last_block != {} and last_block["id"] > 500:
        remote_last_block = (await node_interface.get_block(starting_from - 1))["block"]
        if remote_last_block["hash"] != last_block["hash"]:
            offset, limit = starting_from - 500, 500
            remote_blocks = await node_interface.get_blocks(offset, limit)
            local_blocks = await db.get_blocks(offset, limit)
            local_blocks = local_blocks[: len(remote_blocks)]
            local_blocks.reverse()
            remote_blocks.reverse()
            for idx, local_block in enumerate(local_blocks):
                if local_block["block"]["hash"] == remote_blocks[idx]["block"]["hash"]:
                    last_common_block = local_block["block"]["id"]
                    local_cache = local_blocks[:idx]
                    local_cache.reverse()
                    await db.remove_blocks(last_common_block + 1)
                    break

    limit = 1000
    while True:
        i = await db.get_next_block_id()
        try:
            blocks = await node_interface.get_blocks(i, limit)
        except Exception:
            NodesManager.sync()
            break

        try:
            _, last_block = await calculate_difficulty()
            if not blocks:
                if last_block["id"] > starting_from:
                    NodesManager.update_last_message(node_url)
                    if timestamp() - last_block["timestamp"] < 86400:
                        txs_hashes = await db.get_block_transaction_hashes(last_block["hash"])
                        await propagate(
                            "push_block",
                            {
                                "block_content": last_block["content"],
                                "txs": txs_hashes,
                                "block_no": last_block["id"],
                            },
                            node_url,
                        )
                break
            assert await create_blocks(blocks)
        except Exception:
            if local_cache is not None:
                await db.delete_blocks(last_common_block)
                await create_blocks(local_cache)
            return


async def sync_blockchain(node_url: str = None):
    try:
        await _sync_blockchain(node_url)
    except Exception:
        return


async def propagate_old_transactions(propagate_txs):
    db = state.get_db()
    await db.update_pending_transactions_propagation_time([sha256(tx_hex) for tx_hex in propagate_txs])
    for tx_hex in propagate_txs:
        await propagate("push_tx", {"tx_hex": tx_hex})


def run_in_background(async_fn, *args):
    def _runner():
        asyncio.run(async_fn(*args))

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
