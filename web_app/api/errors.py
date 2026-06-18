"""Blueprint JSON error handlers."""

from flask import jsonify

from api import api_bp
from api.exceptions import AppError, DatabaseConnectionError, InputValidationError, SecurityError
from logger import api_logger as logger


@api_bp.errorhandler(AppError)
def handle_app_error(error):
    logger.error(f"[{error.code}] {error.message} | Original: {getattr(error, 'original_error', None)}")
    return jsonify({'error': error.message, 'code': error.code}), error.status_code


@api_bp.errorhandler(DatabaseConnectionError)
def handle_db_error(error):
    if error.original_error:
        logger.error(f"Database connection error: {error.original_error}")
    return jsonify({'error': "Service temporarily unavailable", 'code': error.code}), 503


@api_bp.errorhandler(InputValidationError)
def handle_validation_error(error):
    logger.info(f"[{error.code}] Invalid input: {error.message}")
    return jsonify({'error': error.message, 'code': error.code}), error.status_code


@api_bp.errorhandler(SecurityError)
def handle_security_error(error):
    logger.warning(f"[{error.code}] Security incident: {error.message}")
    return jsonify({'error': "Access denied", 'code': error.code}), 403


@api_bp.errorhandler(Exception)
def handle_generic_error(error):
    logger.exception(f"Unexpected error: {str(error)}")
    return jsonify({'error': "An unexpected error occurred", 'code': "ERR_001"}), 500
