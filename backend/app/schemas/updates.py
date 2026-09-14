from pydantic import model_validator


def reject_blanking(*fields: str):
    """
    Refuse an update that explicitly sets a required field to null.

    A partial update uses null to mean "not given", but a client that really
    sends `{"date": null}` is asking to blank a column the record cannot do
    without. That is a 422, not a crash at the database.
    """

    @model_validator(mode="after")
    def check(self):
        blanked = [
            field
            for field in fields
            if field in self.model_fields_set and getattr(self, field) is None
        ]
        if blanked:
            raise ValueError(f"cannot be blanked: {', '.join(blanked)}")
        return self

    return check
