# Contributing to SatQuery AI

Thank you for your interest in contributing to SatQuery AI! We welcome contributions from everyone. This document provides guidelines and instructions for contributing.

## Code of Conduct

Please be respectful and constructive in all interactions. We aim to maintain a welcoming and inclusive community.

## Getting Started

### Prerequisites
- Python 3.12+
- Node.js 20+
- Git
- Docker (optional, for containerized development)

### Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/satquery-ai.git
   cd satquery-ai
   ```

2. **Set up Python backend**
   ```bash
   cd backend
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On Unix:
   source venv/bin/activate
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

3. **Set up frontend**
   ```bash
   cd ../frontend
   npm install
   ```

4. **Configure environment**
   ```bash
   cd ../backend
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Install pre-commit hooks**
   ```bash
   pip install pre-commit
   pre-commit install
   ```

## Development Workflow

### Running Locally

**Backend:**
```bash
cd backend
python run.py
# API available at http://localhost:8000
```

**Frontend:**
```bash
cd frontend
npm run dev
# Frontend available at http://localhost:5173
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_api.py

# Run tests matching pattern
pytest -k "test_upload"
```

### Code Quality Checks

```bash
# Run linting
pylint backend/app/
flake8 backend/app/

# Format code
black backend/app/
isort backend/app/

# Type checking
mypy backend/app/

# Frontend linting
cd frontend && npm run lint

# Frontend formatting
cd frontend && npm run format
```

## Pull Request Process

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Follow the code style guidelines below
   - Add tests for new functionality
   - Update documentation as needed

3. **Run tests and checks**
   ```bash
   pytest --cov
   pylint backend/app/
   black --check backend/app/
   mypy backend/app/
   ```

4. **Commit with conventional commits**
   ```bash
   git commit -m "feat: add new feature description"
   git commit -m "fix: resolve issue with component"
   git commit -m "docs: update API documentation"
   ```
   Use prefixes: `feat:`, `fix:`, `docs:`, `style:`, `refactor:`, `test:`, `chore:`

5. **Push and create Pull Request**
   ```bash
   git push origin feature/your-feature-name
   ```

6. **PR Description Template**
   ```markdown
   ## Description
   Brief description of changes

   ## Type of Change
   - [ ] Bug fix
   - [ ] New feature
   - [ ] Breaking change
   - [ ] Documentation update

   ## Testing
   Describe testing performed

   ## Checklist
   - [ ] Tests pass locally
   - [ ] Code follows style guidelines
   - [ ] Self-review completed
   - [ ] Documentation updated
   - [ ] No new warnings generated
   ```

## Code Style Guidelines

### Python
- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/)
- Use `black` for formatting (line length: 100)
- Use `isort` for import sorting
- Type hints required for all functions
- Docstrings for all public functions/classes
- Example:
  ```python
  async def process_image(
      image_path: Path,
      config: ImageConfig
  ) -> ProcessedImage:
      """Process satellite image according to config.
      
      Args:
          image_path: Path to the image file
          config: Image processing configuration
          
      Returns:
          ProcessedImage with metadata and processed data
          
      Raises:
          FileNotFoundError: If image file doesn't exist
          ValueError: If configuration is invalid
      """
      # Implementation
  ```

### TypeScript/React
- Follow [Airbnb JavaScript Style Guide](https://github.com/airbnb/javascript)
- Use ESLint and Prettier for formatting
- Functional components with hooks (no class components)
- Type all props with TypeScript interfaces
- Example:
  ```typescript
  interface ImageUploadProps {
    onUploadComplete: (uploadId: string) => void;
    maxSizeMB?: number;
  }

  export const ImageUpload: React.FC<ImageUploadProps> = ({
    onUploadComplete,
    maxSizeMB = 100,
  }) => {
    // Implementation
  };
  ```

## Testing Guidelines

- Write tests for all new features
- Aim for 80%+ code coverage
- Use descriptive test names: `test_process_geotiff_with_valid_projection`
- Organize tests by module
- Example:
  ```python
  async def test_upload_geotiff_returns_valid_id(client, sample_geotiff):
      """Test that uploading valid GeoTIFF returns upload_id."""
      response = await client.post(
          "/upload",
          files={"file": sample_geotiff}
      )
      assert response.status_code == 200
      assert "upload_id" in response.json()
  ```

## Documentation

- Update README.md for user-facing changes
- Update ARCHITECTURE.md for structural changes
- Include docstrings in code
- Add comments for complex logic
- Keep examples up-to-date

## Security

- Never commit secrets or API keys
- Report security vulnerabilities privately to maintainers
- Keep dependencies up-to-date
- Follow OWASP best practices
- Run `bandit` for security checks:
  ```bash
  bandit -r backend/app/
  ```

## Performance

- Profile code before optimizing: `python -m cProfile -s cumtime script.py`
- Test with production-like data volumes
- Monitor memory usage for large datasets
- Document performance benchmarks

## Questions?

- Open an issue for bugs and feature requests
- Use discussions for questions and ideas
- Check existing issues before creating new ones

## Attribution

Contributors will be recognized in the README and CHANGELOG.

Thank you for contributing to SatQuery AI! 🎉
