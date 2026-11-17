
class RiskService:
    """Calculates a stock verification risk score from 0 to 100."""

    @staticmethod
    def calculate(expected_quantity, physical_quantity, reorder_level=0):
        expected = int(expected_quantity)
        physical = int(physical_quantity)
        reorder = int(reorder_level)

        if min(expected, physical, reorder) < 0:
            raise ValueError("Quantities cannot be negative.")

        difference = physical - expected
        absolute_difference = abs(difference)

        # Maximum 50 points for stock discrepancy.
        discrepancy_score = 0
        if expected > 0:
            discrepancy_score = min(
                50, (absolute_difference / expected) * 50
            )
        elif physical > 0:
            discrepancy_score = 50

        # 30 points when expected stock is at or below reorder level.
        low_stock_score = 30 if expected <= reorder else 0

        # 20 points for stock physically found when system stock is zero.
        unexpected_stock_score = (
            20 if expected == 0 and physical > 0 else 0
        )

        score = min(
            100,
            round(
                discrepancy_score
                + low_stock_score
                + unexpected_stock_score
            )
        )

        level = RiskService.level_for(score)

        return {
            "score": score,
            "level": level,
            "difference": difference,
            "absolute_difference": absolute_difference,
            "factors": {
                "discrepancy": round(discrepancy_score, 2),
                "low_stock": low_stock_score,
                "unexpected_stock": unexpected_stock_score,
            },
        }

    @staticmethod
    def level_for(score):

        if score >= 70:
            return "HIGH"

        if score >= 35:
            return "MEDIUM"

        return "LOW"

    @staticmethod
    def stock_level_risk(quantity, reorder_level):
        """Risk from the current stock level alone (used for prioritising)."""

        quantity = int(quantity)
        reorder = int(reorder_level)

        if quantity <= 0:
            return 90

        if quantity <= reorder:
            # 40 at the reorder level, rising towards 69 as stock nears zero.
            return round(40 + 29 * (1 - quantity / max(reorder, 1)))

        return 0
