import re

from asgiref.sync import async_to_sync
from django.http import JsonResponse
from django.http import HttpResponseRedirect

from node_api.network import NodeInterface, NodesManager
from node_api.network_utils import ip_is_local
from node_api import state
from node_api.services import propagate, propagate_old_transactions, run_in_background


class NodeNetworkMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        normalized_path = re.sub(r"/+", "/", request.path)
        if normalized_path != request.path:
            query = f"?{request.META['QUERY_STRING']}" if request.META.get("QUERY_STRING") else ""
            return HttpResponseRedirect(f"{normalized_path}{query}")

        sender_node = request.headers.get("Sender-Node")
        if sender_node:
            NodesManager.add_node(sender_node)

        nodes = NodesManager.get_recent_nodes()
        hostname = request.get_host().split(":")[0]

        if (nodes and not state.started) or ip_is_local(hostname) or hostname == "localhost":
            try:
                node_url = nodes[0]
                peers = async_to_sync(NodesManager.request)(f"{node_url}/get_nodes")
                nodes.extend(peers["result"])
                NodesManager.sync()
            except Exception:
                pass

            if not (ip_is_local(hostname) or hostname == "localhost"):
                state.started = True
                state.self_url = request.build_absolute_uri("/").strip("/")

                for candidate in (state.self_url, state.self_url.replace("http://", "https://")):
                    try:
                        nodes.remove(candidate)
                    except ValueError:
                        pass

                NodesManager.sync()

                try:
                    async_to_sync(propagate)("add_node", {"url": state.self_url})
                    cousin_nodes = []
                    for url in nodes:
                        cousin_nodes.extend(async_to_sync(NodeInterface(url).get_nodes)())
                    async_to_sync(propagate)("add_node", {"url": state.self_url}, nodes=cousin_nodes)
                except Exception:
                    pass

        propagate_txs = []
        try:
            db = state.get_db()
            propagate_txs = async_to_sync(db.get_need_propagate_transactions)()
        except Exception:
            propagate_txs = []

        try:
            response = self.get_response(request)
        except Exception as exc:
            return JsonResponse(
                {"ok": False, "error": f"Uncaught {type(exc).__name__} exception"},
                status=500,
            )
        response["Access-Control-Allow-Origin"] = "*"

        if propagate_txs:
            run_in_background(propagate_old_transactions, propagate_txs)

        return response
