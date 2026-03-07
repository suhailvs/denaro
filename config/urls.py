from django.urls import path

from node_api import views

urlpatterns = [
    path("", views.root),
    path("push_tx", views.push_tx),
    path("push_block", views.push_block),
    path("sync_blockchain", views.sync_blockchain_view),
    path("get_mining_info", views.get_mining_info),
    path("get_address_info", views.get_address_info),
    path("add_node", views.add_node),
    path("get_nodes", views.get_nodes),
    path("get_pending_transactions", views.get_pending_transactions),
    path("get_transaction", views.get_transaction),
    path("get_block", views.get_block),
    path("get_blocks", views.get_blocks),
]
