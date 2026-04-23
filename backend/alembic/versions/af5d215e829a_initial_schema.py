"""initial_schema

Revision ID: af5d215e829a
Revises:
Create Date: 2026-04-23

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "af5d215e829a"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.Text, unique=True, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("phone", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "shops",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("shop_type", sa.Text, server_default="mamak"),
        sa.Column("location_lat", sa.Numeric(9, 6)),
        sa.Column("location_lng", sa.Numeric(9, 6)),
        sa.Column("city", sa.Text, server_default="Kuala Lumpur"),
        sa.Column("is_halal", sa.Boolean, server_default="true"),
        sa.Column("operating_hours", JSONB),
        sa.Column("expo_push_token", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "products",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("shop_id", UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("sku", sa.Text),
        sa.Column("category", sa.Text),
        sa.Column("unit", sa.Text, server_default="unit"),
        sa.Column("avg_cost_price", sa.Numeric(10, 2)),
        sa.Column("avg_selling_price", sa.Numeric(10, 2)),
        sa.Column("spoilage_days", sa.Integer, server_default="3"),
        sa.Column("min_stock_threshold", sa.Numeric(10, 2), server_default="0"),
        sa.Column("reorder_quantity", sa.Numeric(10, 2)),
        sa.Column("demand_elasticity", sa.Numeric(4, 2), server_default="-1.2"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("shop_id", "name", name="uq_shop_product_name"),
    )

    op.create_table(
        "invoices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("shop_id", UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_name", sa.Text),
        sa.Column("invoice_number", sa.Text),
        sa.Column("invoice_date", sa.Date),
        sa.Column("total_amount", sa.Numeric(10, 2)),
        sa.Column("currency", sa.Text, server_default="MYR"),
        sa.Column("raw_image_url", sa.Text, nullable=False),
        sa.Column("ocr_confidence", sa.Numeric(4, 3)),
        sa.Column("ocr_raw_json", JSONB),
        sa.Column("processing_status", sa.Text, server_default="pending"),
        sa.Column("failure_reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "invoice_line_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("invoice_id", UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_name_raw", sa.Text, nullable=False),
        sa.Column("matched_product_id", UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=False),
        sa.Column("unit_raw", sa.Text),
        sa.Column("unit_price", sa.Numeric(10, 2)),
        sa.Column("total_price", sa.Numeric(10, 2)),
        sa.Column("ocr_confidence", sa.Numeric(4, 3)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "inventory_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("shop_id", UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_ref", sa.Text),
        sa.Column("current_qty", sa.Numeric(10, 3), nullable=False, server_default="0"),
        sa.Column("unit", sa.Text, nullable=False),
        sa.Column("cost_price", sa.Numeric(10, 2)),
        sa.Column("purchase_date", sa.Date),
        sa.Column("expiry_date", sa.Date),
        sa.Column("is_depleted", sa.Boolean, server_default="false"),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("shop_id", "product_id", "batch_ref", name="uq_inventory_batch"),
    )

    op.create_table(
        "external_context_cache",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("shop_id", UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("context_type", sa.Text, nullable=False),
        sa.Column("context_date", sa.Date, nullable=False),
        sa.Column("data_json", JSONB, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("shop_id", "context_type", "context_date", name="uq_context_cache"),
    )

    op.create_table(
        "ai_recommendations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("shop_id", UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("recommendation_type", sa.Text, nullable=False),
        sa.Column("status", sa.Text, server_default="active"),
        sa.Column("recommended_action", sa.Text, nullable=False),
        sa.Column("target_quantity", sa.Numeric(10, 2)),
        sa.Column("target_price", sa.Numeric(10, 2)),
        sa.Column("confidence_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("risk_of_inaction", sa.Numeric(10, 2)),
        sa.Column("expected_gain", sa.Numeric(10, 2)),
        sa.Column("reasoning_trace", JSONB, nullable=False),
        sa.Column("external_factors", JSONB),
        sa.Column("glm_explanation", sa.Text),
        sa.Column("feedback_rating", sa.Integer),
        sa.Column("feedback_note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("feedback_rating BETWEEN 1 AND 5", name="ck_feedback_rating"),
    )

    # Indexes
    op.create_index("idx_inventory_shop_product", "inventory_items", ["shop_id", "product_id"])
    op.create_index("idx_invoices_shop_date", "invoices", ["shop_id", "invoice_date"])
    op.create_index("idx_recs_shop_status", "ai_recommendations", ["shop_id", "status"])
    op.create_index("idx_context_cache_lookup", "external_context_cache", ["shop_id", "context_type", "context_date"])


def downgrade() -> None:
    op.drop_index("idx_context_cache_lookup")
    op.drop_index("idx_recs_shop_status")
    op.drop_index("idx_invoices_shop_date")
    op.drop_index("idx_inventory_shop_product")
    op.drop_table("ai_recommendations")
    op.drop_table("external_context_cache")
    op.drop_table("inventory_items")
    op.drop_table("invoice_line_items")
    op.drop_table("invoices")
    op.drop_table("products")
    op.drop_table("shops")
    op.drop_table("users")
