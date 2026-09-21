"""
Categorization Rules: "description contains X -> Category Y".

Rules are learned from the user's own choices during an Import. When several
match a description the longest pattern wins, so "mercado libre" beats
"mercado" and a specific merchant is never swallowed by a generic word.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CategorizationRule
from app.schemas.categorization import (
    CategorizationRuleCreate,
    CategorizationRuleUpdate,
)
from app.services.categories import get_category
from app.services.errors import Conflict, NotFound


async def get_rule(db: AsyncSession, rule_id: uuid.UUID) -> CategorizationRule:
    rule = await db.get(CategorizationRule, rule_id)
    if rule is None:
        raise NotFound(f"no Categorization Rule with id {rule_id}")
    return rule


async def list_rules(db: AsyncSession) -> list[CategorizationRule]:
    """Longest pattern first, which is also the order matching resolves in."""
    result = await db.execute(
        select(CategorizationRule).order_by(
            func.length(CategorizationRule.pattern).desc(),
            CategorizationRule.pattern,
        )
    )
    return list(result.scalars().all())


async def rule_for(db: AsyncSession, pattern: str) -> CategorizationRule | None:
    """
    The rule that already maps that pattern, if there is one.

    Case-insensitively, which is looser than the unique constraint on purpose:
    matching ignores case, so a rule for "PedidosYa" and one for "pedidosya"
    are the same rule said twice, whatever the database would let through.
    Lowered on both sides rather than case-folded, because the comparison is
    the database's and `lower()` is the only one of the two it knows.
    """
    result = await db.execute(
        select(CategorizationRule).where(
            func.lower(CategorizationRule.pattern) == pattern.strip().lower()
        )
    )
    return result.scalars().first()


async def check_rule(db: AsyncSession, data: CategorizationRuleCreate) -> None:
    """Everything learning it would check, without learning anything."""
    await _checked(db, data)


async def build_rule(
    db: AsyncSession, data: CategorizationRuleCreate
) -> CategorizationRule:
    """
    A checked rule, added to the session but not committed.

    The commit is the caller's, so a rule learned by accepting a Suggestion is
    written in the same commit as the Suggestion that proposed it.
    """
    pattern = await _checked(db, data)
    rule = CategorizationRule(**{**data.model_dump(), "pattern": pattern})
    db.add(rule)
    # The id is the column default, which only exists once the row is flushed.
    await db.flush()
    return rule


async def _checked(db: AsyncSession, data: CategorizationRuleCreate) -> str:
    """The pattern as it would be stored, held to what a new rule must be."""
    await get_category(db, data.category_id)
    pattern = data.pattern.strip()
    if await rule_for(db, pattern) is not None:
        raise Conflict(f"a Categorization Rule for '{pattern}' already exists")
    return pattern


async def create_rule(
    db: AsyncSession, data: CategorizationRuleCreate
) -> CategorizationRule:
    rule = await build_rule(db, data)
    await db.commit()
    await db.refresh(rule)
    return rule


async def update_rule(
    db: AsyncSession, rule_id: uuid.UUID, changes: CategorizationRuleUpdate
) -> CategorizationRule:
    rule = await get_rule(db, rule_id)
    changed = changes.model_dump(exclude_unset=True)
    if "category_id" in changed:
        await get_category(db, changed["category_id"])
    for field, value in changed.items():
        setattr(rule, field, value)
    await db.commit()
    await db.refresh(rule)
    return rule


async def delete_rule(db: AsyncSession, rule_id: uuid.UUID) -> None:
    await db.delete(await get_rule(db, rule_id))
    await db.commit()


def match(rules: list[CategorizationRule], description: str) -> uuid.UUID | None:
    """The Category of the longest rule whose pattern the description contains."""
    haystack = (description or "").casefold()
    for rule in sorted(rules, key=lambda rule: len(rule.pattern), reverse=True):
        if rule.pattern.casefold() in haystack:
            return rule.category_id
    return None
