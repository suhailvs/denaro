from django.contrib.postgres.fields import ArrayField
from django.db import models


class Block(models.Model):
    id = models.AutoField(primary_key=True)
    hash = models.CharField(max_length=64, unique=True, null=True, blank=True)
    content = models.TextField()
    address = models.CharField(max_length=128)
    random = models.BigIntegerField()
    difficulty = models.DecimalField(max_digits=3, decimal_places=1)
    reward = models.DecimalField(max_digits=14, decimal_places=6)
    timestamp = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "blocks"
        managed = False


class Transaction(models.Model):
    block_hash = models.ForeignKey(
        Block,
        on_delete=models.CASCADE,
        db_column="block_hash",
        to_field="hash",
        related_name="transactions",
    )
    tx_hash = models.CharField(max_length=64, unique=True, null=True, blank=True)
    tx_hex = models.TextField(null=True, blank=True)
    inputs_addresses = ArrayField(models.TextField(), null=True, blank=True)
    outputs_addresses = ArrayField(models.TextField(), null=True, blank=True)
    outputs_amounts = ArrayField(models.BigIntegerField(), null=True, blank=True)
    fees = models.DecimalField(max_digits=14, decimal_places=6)

    class Meta:
        db_table = "transactions"
        managed = False
        indexes = [
            models.Index(fields=["block_hash"], name="block_hash_idx"),
        ]


class UnspentOutput(models.Model):
    tx_hash = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        db_column="tx_hash",
        to_field="tx_hash",
        related_name="unspent_outputs",
        null=True,
        blank=True,
    )
    index = models.SmallIntegerField()
    address = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "unspent_outputs"
        managed = False
        indexes = [
            models.Index(fields=["tx_hash"], name="tx_hash_idx"),
        ]


class PendingTransaction(models.Model):
    tx_hash = models.CharField(max_length=64, unique=True, null=True, blank=True)
    tx_hex = models.TextField(null=True, blank=True)
    inputs_addresses = ArrayField(models.TextField(), null=True, blank=True)
    fees = models.DecimalField(max_digits=14, decimal_places=6)
    propagation_time = models.DateTimeField()

    class Meta:
        db_table = "pending_transactions"
        managed = False


class PendingSpentOutput(models.Model):
    tx_hash = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        db_column="tx_hash",
        to_field="tx_hash",
        related_name="pending_spent_outputs",
        null=True,
        blank=True,
    )
    index = models.SmallIntegerField()

    class Meta:
        db_table = "pending_spent_outputs"
        managed = False
