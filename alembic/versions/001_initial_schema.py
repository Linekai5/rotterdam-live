"""Initial PostGIS schema for Rotterdam Live.

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-12 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import geoalchemy2

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. PostGIS Extension
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

    # 2. rotterdam_districts table
    op.create_table(
        "rotterdam_districts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("district_type", sa.String(length=32), nullable=False),
        sa.Column("properties", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                spatial_index=True,
            ),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rotterdam_districts_code", "rotterdam_districts", ["code"])
    op.create_index("ix_rotterdam_districts_name", "rotterdam_districts", ["name"])

    # 3. live_events table
    op.create_table(
        "live_events",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("subcategory", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("district", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="GEOMETRY",
                srid=4326,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                spatial_index=True,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_live_events_category", "live_events", ["category"])
    op.create_index("ix_live_events_subcategory", "live_events", ["subcategory"])
    op.create_index("ix_live_events_severity", "live_events", ["severity"])
    op.create_index("ix_live_events_timestamp", "live_events", ["timestamp"])
    op.create_index("ix_live_events_expires_at", "live_events", ["expires_at"])
    op.create_index("ix_live_events_district", "live_events", ["district"])
    op.create_index(
        "idx_live_events_category_time", "live_events", ["category", "timestamp"]
    )
    op.create_index(
        "idx_live_events_active", "live_events", ["expires_at", "category"]
    )


def downgrade() -> None:
    op.drop_table("live_events")
    op.drop_table("rotterdam_districts")
