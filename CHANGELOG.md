# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive test suite with 80%+ code coverage
- GitHub Actions CI/CD pipeline (tests, linting, security scanning)
- Enhanced project documentation (CONTRIBUTING.md, ARCHITECTURE.md, API_REFERENCE.md)
- Code quality tools (pylint, black, flake8, ESLint, Prettier)
- Pre-commit hooks for automated code quality checks
- Security scanning with Bandit and Dependabot
- Structured logging with python-json-logger
- Sentry integration for error tracking
- Alembic database migration framework
- Performance benchmarking with k6/Locust
- API rate limiting and request queuing
- Database connection pooling and optimization
- Comprehensive error handling and logging

### Changed
- Improved API response consistency and error messages
- Enhanced environment configuration documentation
- Streamlined Docker build process
- Optimized dependency management

### Fixed
- Database transaction handling
- CORS header validation
- File upload validation edge cases

## [1.0.0] - 2024-09-01

### Added
- Initial release of SatQuery AI
- FastAPI backend with agentic architecture
- React frontend with Leaflet mapping
- Docker & Docker Compose deployment
- Support for GeoTIFF, SAR, optical imagery
- Vision-language model integration
- Change detection and segmentation capabilities
- SQLite storage with trace persistence
- Multi-model registry system
- Cloud deployment support (Render.yaml)

### Features
- Image upload and preprocessing pipeline
- Agentic query processing with planner/dispatcher/validator
- Evidence fusion with confidence estimation
- Real-time result streaming
- Geospatial coordinate transformation
- Multi-resolution tile caching
- Comprehensive job tracking and status monitoring

[Unreleased]: https://github.com/yourusername/satquery-ai/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/yourusername/satquery-ai/releases/tag/v1.0.0
