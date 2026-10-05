class NavigationManager:
    """Helper methods for calculating next/previous image indices and bounds checks."""

    @staticmethod
    def can_navigate_previous(index: int) -> bool:
        return index > 0

    @staticmethod
    def can_navigate_next(index: int, total: int) -> bool:
        return 0 <= index < total - 1

    @staticmethod
    def get_previous_index(index: int) -> int | None:
        if index > 0:
            return index - 1
        return None

    @staticmethod
    def get_next_index(index: int, total: int, wrap: bool = False) -> int | None:
        if index < total - 1:
            return index + 1
        elif wrap and total > 0:
            return 0
        return None
