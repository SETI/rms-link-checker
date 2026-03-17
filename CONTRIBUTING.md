# Contributing to rms-link-checker

Thank you for your interest in contributing to rms-link-checker! This document provides
guidelines and instructions for contributing to the project.

## Code of Conduct

We expect all contributors to follow our Code of Conduct, which ensures a welcoming and
inclusive environment for everyone. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally:

   ```bash
   git clone https://github.com/your-username/rms-link-checker.git
   cd rms-link-checker
   ```

3. Create a virtual environment and install the package with dev dependencies:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -e ".[dev]"
   ```

## Development Workflow

1. Create a new branch for your feature or bugfix:

   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b bugfix/issue-number
   ```

2. Make your changes, following our coding standards
3. Write or update tests as necessary (we follow TDD — tests first!)
4. Run the tests to ensure they pass:

   ```bash
   pytest -n auto --cov
   ```

5. Run all checks with the provided script:

   ```bash
   ./scripts/run-all-checks.sh
   ```

6. Commit your changes with a descriptive message:

   ```bash
   git commit -m "feat: add feature description"
   ```

7. Push your branch to your fork:

   ```bash
   git push origin feature/your-feature-name
   ```

8. Open a Pull Request on GitHub

## Coding Standards

We follow these standards for all code contributions:

- **Python Style**: Follow PEP 8 (enforced via `ruff`)
- **Type Hints**: Use type hints for all function parameters and return values
- **Docstrings**: Document all classes and methods with Google-style docstrings
- **Testing**: Include unit tests for new functionality (TDD approach)
- **Compatibility**: Ensure compatibility with Python 3.10+

## Pull Request Process

1. Ensure all tests pass
2. Update documentation if necessary
3. Make sure your code is properly formatted and passes both `ruff` and `mypy`
4. Request a review from a maintainer
5. Address any feedback from reviewers

The maintainers will merge your PR once it meets all requirements.

## Testing

We use pytest for testing. To run the tests with coverage:

```bash
pytest -n auto --cov
```

For more verbose output:

```bash
pytest -v
```

To run a specific test file:

```bash
pytest tests/test_url_utils.py
```

## Documentation

We use Sphinx for documentation. To build the docs:

```bash
cd docs
make html
```

The generated documentation will be in `docs/_build/html`.

## Reporting Issues

If you find a bug or have a suggestion for improvement:

1. Check if the issue already exists in the GitHub issue tracker
2. If not, create a new issue with:
   - A clear, descriptive title
   - A detailed description of the issue
   - Steps to reproduce (for bugs)
   - Your environment information (Python version, OS, etc.)
   - Any relevant logs or screenshots

Thank you for contributing to rms-link-checker!
