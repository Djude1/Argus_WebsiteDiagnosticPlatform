# Contributing to OpenAI Device For Visual Impairment

Thank you for your interest in contributing to this open-source accessibility project! We welcome contributions that help make visual AI technology more accessible to people with visual impairments.

## How to Contribute

### 🐛 Bug Reports
If you encounter a bug, please report it by:
1. Creating a new issue using the [Bug Report Template](.github/ISSUE_TEMPLATE/bug_report.md)
2. Include steps to reproduce, expected behavior, and actual behavior
3. Screenshots or error logs (if applicable)

### 💡 Feature Suggestions
We're always looking for ways to improve! To suggest a new feature:
1. Create a new issue using the [Feature Request Template](.github/ISSUE_TEMPLATE/feature_request.md)
2. Explain the problem you're trying to solve
3. Provide detailed use cases and examples

### 🚀 Pull Requests
Pull requests are welcome! Here's how to contribute:

1. **Fork** the repository
2. **Clone** your fork: `git clone https://github.com/your-username/OpenAIDevice_For_VisualImpairment.git`
3. **Create** a feature branch: `git checkout -b feature/amazing-feature`
4. **Make** your changes
5. **Test** your changes thoroughly
6. **Commit** your changes: `git commit -m 'Add amazing feature'`
7. **Push** to the branch: `git push origin feature/amazing-feature`
8. **Open** a Pull Request with a clear description of your changes

## Development Setup

### Prerequisites
- Python 3.8 or higher
- Node.js 16 or higher (for web interface)
- Git

### Quick Start
```bash
# Clone the repository
git clone https://github.com/OpenAIDevice-For-VisualImpairment/OpenAIDevice_For_VisualImpairment.git
cd OpenAIDevice_For_VisualImpairment

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
cd web_interface && npm install
cd ..

# Run the application
python main.py
```

### Running Tests
```bash
# Run all tests
python -m pytest

# Run with coverage
python -m pytest --cov=src

# Run specific test file
python -m pytest tests/test_accessibility.py
```

## Coding Standards

### Python Code
- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) style guidelines
- Use type hints for function parameters and return values
- Keep functions focused and under 50 lines when possible
- Write docstrings for all public classes, functions, and methods
- Use black for code formatting
- Use flake8 for linting

### JavaScript/TypeScript Code
- Use ES6+ features
- Follow the Airbnb JavaScript Style Guide
- Use Prettier for code formatting
- Include JSDoc comments for complex functions
- Write unit tests for all new features

### Accessibility Guidelines
- Ensure all UI elements have proper ARIA labels
- Test screen reader compatibility
- Provide keyboard navigation support
- Use color contrast compliant with WCAG 2.1 AA standards
- Include alt text for all images
- Ensure content is navigable by keyboard alone

## Commit Message Guidelines

We use [Conventional Commits](https://www.conventionalcommits.org/) for consistent commit messages.

Format: `<type>(<scope>): <description>`

### Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes
- `refactor`: Code refactoring
- `test`: Adding or fixing tests
- `chore`: Build process or auxiliary tool changes

### Examples:
```bash
feat: add voice control for navigation
fix: resolve screen reader focus issue
docs: update installation guide
refactor: optimize image processing pipeline
test: add unit tests for speech recognition
```

## Reporting Security Issues

If you discover a security vulnerability, please follow our [Security Policy](SECURITY.md). Please do not create public issues for security concerns.

## Getting Help

- Join our [Discussions](https://github.com/OpenAIDevice-For-VisualImpairment/OpenAIDevice_For_VisualImpairment/discussions)
- Check the [Wiki](https://github.com/OpenAIDevice-For-VisualImpairment/OpenAIDevice_For_VisualImpairment/wiki) for guides and FAQs
- Contact maintainers via GitHub issues for urgent matters

## Recognition

Contributors will be recognized in the project's [Contributors List](CONTRIBUTORS.md). For major contributions, we'd be happy to add you to our team of maintainers.

## License

By contributing to this project, you agree that your contributions will be licensed under the [MIT License](LICENSE).

---

We appreciate your help in making this project better for the community! 🙏
