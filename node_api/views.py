from asgiref.sync import async_to_sync
from asyncpg import UniqueViolationError
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response

from core.constants import VERSION
from core.helpers import sha256, timestamp
from core.manager import (
    Manager,
    clear_pending_transactions,
    create_block,
    get_difficulty,
    get_transactions_merkle_tree,
    split_block_content,
)
from transactions import Transaction
from node_api import state
from node_api.network import NodesManager
from node_api.services import propagate, run_in_background, sync_blockchain
from node_api.throttles import (
    AddNodeThrottle,
    AddressInfoThrottle,
    BlockThrottle,
    BlocksThrottle,
    SyncThrottle,
    TransactionThrottle,
)


def _param(request, key, default=None):
    if key in request.query_params:
        return request.query_params.get(key)
    if isinstance(request.data, dict):
        return request.data.get(key, default)
    return default


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("1", "true", "yes", "on")


@api_view(["GET"])
def root(request):
    db = state.get_db()
    return Response({"version": VERSION, "unspent_outputs_hash": async_to_sync(db.get_unspent_outputs_hash)()})


@api_view(["GET", "POST"])
def push_tx(request):
    db = state.get_db()
    tx_hex = _param(request, "tx_hex")
    if not tx_hex:
        return Response({"ok": False, "error": "tx_hex is required"}, status=400)

    tx = async_to_sync(Transaction.from_hex)(tx_hex)
    tx_hash = tx.hash()
    if tx_hash in state.transactions_cache:
        return Response({"ok": False, "error": "Transaction just added"})

    try:
        if async_to_sync(db.add_pending_transaction)(tx):
            sender_node = request.headers.get("Sender-Node")
            if sender_node:
                NodesManager.update_last_message(sender_node)
            run_in_background(propagate, "push_tx", {"tx_hex": tx_hex})
            state.transactions_cache.append(tx_hash)
            return Response({"ok": True, "result": "Transaction has been accepted"})
        return Response({"ok": False, "error": "Transaction has not been added"})
    except UniqueViolationError:
        return Response({"ok": False, "error": "Transaction already present"})


@api_view(["GET", "POST"])
def push_block(request):
    if state.is_syncing:
        return Response({"ok": False, "error": "Node is already syncing"})

    db = state.get_db()
    block_content = _param(request, "block_content", "")
    txs = _param(request, "txs", "")
    block_no = _param(request, "block_no")

    if isinstance(request.data, dict):
        if "id" in request.data:
            block_no = request.data.get("id")
        if "block_no" in request.data:
            block_no = request.data.get("block_no")

    if isinstance(txs, str):
        txs = txs.split(",")
        if txs == [""]:
            txs = []

    if block_no is not None:
        block_no = int(block_no)

    previous_hash = split_block_content(block_content)[0]
    next_block_id = async_to_sync(db.get_next_block_id)()

    if block_no is None:
        previous_block = async_to_sync(db.get_block)(previous_hash)
        if previous_block is None:
            sender_node = request.headers.get("Sender-Node")
            if sender_node:
                run_in_background(sync_blockchain, sender_node)
                return Response(
                    {
                        "ok": False,
                        "error": "Previous hash not found, had to sync according to sender node, block may have been accepted",
                    }
                )
            return Response({"ok": False, "error": "Previous hash not found"})
        block_no = previous_block["id"] + 1

    if next_block_id < block_no:
        run_in_background(sync_blockchain, request.headers.get("Sender-Node"))
        return Response(
            {
                "ok": False,
                "error": "Blocks missing, had to sync according to sender node, block may have been accepted",
            }
        )
    if next_block_id > block_no:
        return Response({"ok": False, "error": "Too old block"})

    final_transactions = []
    hashes = []
    for tx_hex in txs:
        if len(tx_hex) == 64:
            hashes.append(tx_hex)
        else:
            final_transactions.append(async_to_sync(Transaction.from_hex)(tx_hex))

    if hashes:
        pending_transactions = async_to_sync(db.get_pending_transactions_by_hash)(hashes)
        if len(pending_transactions) < len(hashes):
            sender_node = request.headers.get("Sender-Node")
            if sender_node:
                run_in_background(sync_blockchain, sender_node)
                return Response(
                    {
                        "ok": False,
                        "error": "Transaction hash not found, had to sync according to sender node, block may have been accepted",
                    }
                )
            return Response({"ok": False, "error": "Transaction hash not found"})
        final_transactions.extend(pending_transactions)

    if not async_to_sync(create_block)(block_content, final_transactions):
        return Response({"ok": False})

    sender_node = request.headers.get("Sender-Node")
    if sender_node:
        NodesManager.update_last_message(sender_node)

    run_in_background(
        propagate,
        "push_block",
        {
            "block_content": block_content,
            "txs": [tx.hex() for tx in final_transactions] if len(final_transactions) < 10 else txs,
            "block_no": block_no,
        },
    )
    return Response({"ok": True})


@api_view(["GET"])
@throttle_classes([SyncThrottle])
def sync_blockchain_view(request):
    if state.is_syncing:
        return Response({"ok": False, "error": "Node is already syncing"})

    state.is_syncing = True
    try:
        async_to_sync(sync_blockchain)(_param(request, "node_url"))
    finally:
        state.is_syncing = False
    return Response({"ok": True})


@api_view(["GET"])
def get_mining_info(request):
    db = state.get_db()
    Manager.difficulty = None
    difficulty, last_block = async_to_sync(get_difficulty)()
    pending_transactions = async_to_sync(db.get_pending_transactions_limit)(hex_only=True)
    pending_transactions = sorted(pending_transactions)

    if state.last_pending_transactions_clean[0] < timestamp() - 600:
        state.last_pending_transactions_clean[0] = timestamp()
        run_in_background(clear_pending_transactions, pending_transactions)

    return Response(
        {
            "ok": True,
            "result": {
                "difficulty": difficulty,
                "last_block": last_block,
                "pending_transactions": pending_transactions[:10],
                "pending_transactions_hashes": [sha256(tx) for tx in pending_transactions],
                "merkle_root": get_transactions_merkle_tree(pending_transactions[:10]),
            },
        }
    )


@api_view(["GET"])
@throttle_classes([AddressInfoThrottle])
def get_address_info(request):
    db = state.get_db()
    address = _param(request, "address")
    transactions_count_limit = int(_param(request, "transactions_count_limit", 5))
    transactions_count_limit = min(transactions_count_limit, 50)
    show_pending = _as_bool(_param(request, "show_pending", False))
    verify = _as_bool(_param(request, "verify", False))

    outputs = async_to_sync(db.get_spendable_outputs)(address)
    balance = sum(output.amount for output in outputs)

    transactions = []
    if transactions_count_limit > 0:
        address_transactions = async_to_sync(db.get_address_transactions)(
            address, limit=transactions_count_limit, check_signatures=True
        )
        transactions = [
            async_to_sync(db.get_nice_transaction)(tx.hash(), address if verify else None)
            for tx in address_transactions
        ]

    pending_transactions = None
    pending_spent_outputs = None
    if show_pending:
        pending = async_to_sync(db.get_address_pending_transactions)(address, True)
        pending_transactions = [
            async_to_sync(db.get_nice_transaction)(tx.hash(), address if verify else None)
            for tx in pending
        ]
        pending_spent_outputs = async_to_sync(db.get_address_pending_spent_outputs)(address)

    return Response(
        {
            "ok": True,
            "result": {
                "balance": "{:f}".format(balance),
                "spendable_outputs": [
                    {"amount": "{:f}".format(output.amount), "tx_hash": output.tx_hash, "index": output.index}
                    for output in outputs
                ],
                "transactions": transactions,
                "pending_transactions": pending_transactions,
                "pending_spent_outputs": pending_spent_outputs,
            },
        }
    )


@api_view(["GET"])
@throttle_classes([AddNodeThrottle])
def add_node(request):
    url = (_param(request, "url", "") or "").strip("/")
    nodes = NodesManager.get_nodes()

    if url == state.self_url:
        return Response({"ok": False, "error": "Recursively adding node"})
    if url in nodes:
        return Response({"ok": False, "error": "Node already present"})

    try:
        if not async_to_sync(NodesManager.is_node_working)(url):
            return Response({"ok": False, "error": "Could not add node"})
        run_in_background(propagate, "add_node", {"url": url}, url)
        NodesManager.add_node(url)
        return Response({"ok": True, "result": "Node added"})
    except Exception:
        return Response({"ok": False, "error": "Could not add node"})


@api_view(["GET"])
def get_nodes(request):
    return Response({"ok": True, "result": NodesManager.get_recent_nodes()[:100]})


@api_view(["GET"])
def get_pending_transactions(request):
    db = state.get_db()
    txs = async_to_sync(db.get_pending_transactions_limit)(1000)
    return Response({"ok": True, "result": [tx.hex() for tx in txs]})


@api_view(["GET"])
@throttle_classes([TransactionThrottle])
def get_transaction(request):
    db = state.get_db()
    tx_hash = _param(request, "tx_hash")
    tx = async_to_sync(db.get_nice_transaction)(tx_hash)
    if tx is None:
        return Response({"ok": False, "error": "Transaction not found"})
    return Response({"ok": True, "result": tx})


@api_view(["GET"])
@throttle_classes([BlockThrottle])
def get_block(request):
    db = state.get_db()
    block = _param(request, "block")
    full_transactions = _as_bool(_param(request, "full_transactions", False))

    if block.isdecimal():
        block_info = async_to_sync(db.get_block_by_id)(int(block))
        if block_info is None:
            return Response({"ok": False, "error": "Block not found"})
        block_hash = block_info["hash"]
    else:
        block_hash = block
        block_info = async_to_sync(db.get_block)(block_hash)

    if not block_info:
        return Response({"ok": False, "error": "Block not found"})

    return Response(
        {
            "ok": True,
            "result": {
                "block": block_info,
                "transactions": async_to_sync(db.get_block_transactions)(block_hash, hex_only=True)
                if not full_transactions
                else None,
                "full_transactions": async_to_sync(db.get_block_nice_transactions)(block_hash)
                if full_transactions
                else None,
            },
        }
    )


@api_view(["GET"])
@throttle_classes([BlocksThrottle])
def get_blocks(request):
    db = state.get_db()
    offset = int(_param(request, "offset", 0))
    limit = min(int(_param(request, "limit", 1000)), 1000)
    blocks = async_to_sync(db.get_blocks)(offset, limit)
    return Response({"ok": True, "result": blocks})
