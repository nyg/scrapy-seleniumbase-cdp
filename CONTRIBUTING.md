# Contributing to scrapy-seleniumbase-cdp

Thank you for your interest in contributing! This document provides guidelines for contributing to this project.

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/nyg/scrapy-seleniumbase-cdp.git
cd scrapy-seleniumbase-cdp
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest
```

## Code Style

- Follow PEP 8 guidelines
- Use type hints where applicable
- Add docstrings to all public functions and classes

## Submitting Changes

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes
4. Run tests to ensure everything works
5. Commit your changes (`git commit -am 'Add new feature'`)
6. Push to the branch (`git push origin feature/your-feature`)
7. Create a Pull Request

## Reporting Issues

When reporting issues, please include:
- Python version
- Scrapy version
- SeleniumBase version
- A minimal code example that reproduces the issue
- Expected vs actual behavior
