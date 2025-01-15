import logging
from typing import Any, Dict, Tuple, List, Union

logger = logging.getLogger(__name__)

class RuleChecker:
    """Class to check DICOM pattern rules"""

    def __init__(self):
        self.operations = {
            'equals': self._equals,
            'contains': self._contains,
            'contains_all': self._contains_all,
            'contains_any': self._contains_any,
            'starts_with': self._starts_with,
            'ends_with': self._ends_with,
            'regex': self._regex,
            'range': self._range,
            'greater_than': self._greater_than,
            'less_than': self._less_than,
            'not_equals': self._not_equals,
            'not_contains': self._not_contains
        }

    def check_pattern_rules(self, dicom_data: Any, pattern_rules: Dict) -> Tuple[bool, str]:
        """
        Check if DICOM data matches pattern rules
        
        Args:
            dicom_data: DICOM dataset
            pattern_rules: Dictionary containing rules to check
            
        Returns:
            Tuple of (matches, reason)
            matches: True if all rules match, False otherwise
            reason: String explaining why rules didn't match (empty if matched)
        """
        rules = pattern_rules.get('rules', [])
        if not rules:
            return False, "No rules defined"

        for rule in rules:
            if not self._check_rule(dicom_data, rule):
                return False, f"Failed rule: {rule}"

        return True, ""

    def _check_rule(self, dicom_data: Any, rule: Dict) -> bool:
        """Check if DICOM data matches a single rule"""
        tag = rule.get('tag')
        operation = rule.get('operation')
        value = rule.get('value')
        required = rule.get('required', True)

        if not all([tag, operation, value is not None]):
            logger.warning(f"Invalid rule format: {rule}")
            return False

        if tag not in dicom_data:
            return not required

        try:
            dicom_value = str(getattr(dicom_data, tag))
            operation_func = self.operations.get(operation)
            
            if operation_func:
                return operation_func(dicom_value, value)
            else:
                logger.warning(f"Unknown operation: {operation}")
                return False
                
        except Exception as e:
            logger.error(f"Error checking rule {rule}: {str(e)}")
            return False

    def _equals(self, dicom_value: str, rule_value: str) -> bool:
        return dicom_value.lower() == str(rule_value).lower()

    def _contains(self, dicom_value: str, rule_value: str) -> bool:
        return str(rule_value).lower() in dicom_value.lower()

    def _contains_all(self, dicom_value: str, rule_values: List[str]) -> bool:
        dicom_value = dicom_value.lower()
        return all(str(v).lower() in dicom_value for v in rule_values)

    def _contains_any(self, dicom_value: str, rule_values: List[str]) -> bool:
        dicom_value = dicom_value.lower()
        return any(str(v).lower() in dicom_value for v in rule_values)

    def _starts_with(self, dicom_value: str, rule_value: str) -> bool:
        return dicom_value.lower().startswith(str(rule_value).lower())

    def _ends_with(self, dicom_value: str, rule_value: str) -> bool:
        return dicom_value.lower().endswith(str(rule_value).lower())

    def _regex(self, dicom_value: str, pattern: str) -> bool:
        import re
        try:
            return bool(re.search(pattern, dicom_value))
        except re.error:
            logger.error(f"Invalid regex pattern: {pattern}")
            return False

    def _range(self, dicom_value: str, range_dict: Dict[str, Union[int, float]]) -> bool:
        try:
            value = float(dicom_value)
            min_val = float(range_dict.get('min', float('-inf')))
            max_val = float(range_dict.get('max', float('inf')))
            return min_val <= value <= max_val
        except (ValueError, TypeError):
            return False

    def _greater_than(self, dicom_value: str, rule_value: Union[int, float]) -> bool:
        try:
            return float(dicom_value) > float(rule_value)
        except (ValueError, TypeError):
            return False

    def _less_than(self, dicom_value: str, rule_value: Union[int, float]) -> bool:
        try:
            return float(dicom_value) < float(rule_value)
        except (ValueError, TypeError):
            return False

    def _not_equals(self, dicom_value: str, rule_value: str) -> bool:
        return not self._equals(dicom_value, rule_value)

    def _not_contains(self, dicom_value: str, rule_value: str) -> bool:
        return not self._contains(dicom_value, rule_value)
