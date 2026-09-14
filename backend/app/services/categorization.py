"""
Categorization Rules: "description contains X -> Category Y".

Rules are learned from the user's own choices during an Import. When several
match a description the longest pattern wins, so "mercado libre" beats
"mercado" and a specific merchant is never swallowed by a generic word.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
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


async def create_rule(
    db: AsyncSession, data: CategorizationRuleCreate
) -> CategorizationRule:
    await get_category(db, data.category_id)
    rule = CategorizationRule(
        **{**data.model_dump(), "pattern": data.pattern.strip()}
    )
    db.add(rule)
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise Conflict(
            f"a Categorization Rule for '{data.pattern.strip()}' already exists"
        ) from error
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
