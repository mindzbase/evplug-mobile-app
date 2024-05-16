class QueueModel:
    user_id: str
    location_id: str

    def __init__(self, location_id, user_id) -> None:
        self.location_id = location_id
        self.user_id = user_id

    def __eq__(self, other):
        return self.location_id == other.location_id and self.user_id == other.user_id
