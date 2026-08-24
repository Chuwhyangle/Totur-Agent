"""Resolve built-in and user-owned custom personas."""

from datetime import datetime, timezone
from uuid import uuid4

from app.db.models import CustomPersonaRecord
from app.repositories import persona_repository
from app.services.agent.personas import InvalidPersonaError, Persona, get_persona as get_builtin_persona


class CustomPersonaError(ValueError):
    """Custom persona validation or ownership failure."""


class PersonaService:
    """Application service keeping persona persistence out of the chat agent."""

    def resolve(self, *, user_id: str | None, persona_id: str | None) -> Persona:
        if persona_id is None:
            return get_builtin_persona(None)
        try:
            return get_builtin_persona(persona_id)
        except InvalidPersonaError:
            if not user_id:
                raise
            record = persona_repository.get_persona(persona_id, user_id=user_id.strip())
            if record is None or record.status != "ACTIVE":
                raise InvalidPersonaError(persona_id)
            return Persona(
                persona_id=record.id,
                name=record.name,
                description=record.description,
                system_prompt=record.system_prompt,
            )

    def list_for_user(self, user_id: str | None) -> list[Persona]:
        from app.services.agent.personas import list_personas as list_builtin

        result = list_builtin()
        if not user_id or not user_id.strip():
            return result
        result.extend(
            Persona(
                persona_id=record.id,
                name=record.name,
                description=record.description,
                system_prompt=record.system_prompt,
            )
            for record in persona_repository.list_personas(user_id.strip())
        )
        return result

    def create(self, *, user_id: str, name: str, description: str, system_prompt: str) -> CustomPersonaRecord:
        normalized_user = user_id.strip()
        normalized_name = name.strip()
        normalized_description = description.strip()
        normalized_prompt = system_prompt.strip()
        if not normalized_user or not normalized_name or not normalized_description or not normalized_prompt:
            raise CustomPersonaError("user_id, name, description and system_prompt are required")
        if len(normalized_name) > 100 or len(normalized_description) > 500:
            raise CustomPersonaError("name or description is too long")
        now = datetime.now(timezone.utc).isoformat()
        return persona_repository.insert_persona(CustomPersonaRecord(
            id=str(uuid4()), user_id=normalized_user, name=normalized_name,
            description=normalized_description, system_prompt=normalized_prompt,
            status="ACTIVE", created_at=now, updated_at=now,
        ))

    def update(self, *, user_id: str, persona_id: str, name: str, description: str, system_prompt: str) -> CustomPersonaRecord:
        record = persona_repository.get_persona(persona_id, user_id=user_id.strip())
        if record is None:
            raise CustomPersonaError("persona not found")
        if record.status != "ACTIVE":
            raise CustomPersonaError("persona is disabled")
        updated = CustomPersonaRecord(
            id=record.id, user_id=record.user_id, name=name.strip(),
            description=description.strip(), system_prompt=system_prompt.strip(),
            status=record.status, created_at=record.created_at, updated_at=record.updated_at,
        )
        if not updated.name or not updated.description or not updated.system_prompt:
            raise CustomPersonaError("name, description and system_prompt are required")
        if len(updated.name) > 100 or len(updated.description) > 500:
            raise CustomPersonaError("name or description is too long")
        return persona_repository.update_persona(updated)

    def disable(self, *, user_id: str, persona_id: str) -> CustomPersonaRecord:
        record = persona_repository.get_persona(persona_id, user_id=user_id.strip())
        if record is None:
            raise CustomPersonaError("persona not found")
        record.status = "DISABLED"
        return persona_repository.update_persona(record)
