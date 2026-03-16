<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-16 | Updated: 2026-03-16 -->

# screens

## Purpose
Flutter screen widgets representing the main UI pages of the Android companion app. Each screen handles a distinct user flow or feature area.

## Key Files
| File | Description |
|------|-------------|
| `home_screen.dart` | Main home screen with navigation controls |
| `login_screen.dart` | User authentication login form |
| `admin_login_screen.dart` | Administrative login interface |
| `splash_screen.dart` | App initialization and loading screen |
| `settings_screen.dart` | User preferences and app configuration |
| `ar_screen.dart` | AR navigation display screen |
| `contacts_screen.dart` | Emergency contacts management |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `admin/` | Admin-only screens (see `admin/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- Each screen is a StatefulWidget or ConsumerWidget
- Use Navigator for screen transitions
- Follow Material Design 3 guidelines
- Implement proper dispose() for controllers

### Common Patterns
```dart
class MyScreen extends ConsumerStatefulWidget {
  @override
  ConsumerState<MyScreen> createState() => _MyScreenState();
}

class _MyScreenState extends ConsumerState<MyScreen> {
  @override
  Widget build(BuildContext context) {
    final provider = ref.watch(myProvider);
    return Scaffold(...);
  }
}
```

### Testing Requirements
- Widget tests in `test/screens/`
- Test navigation flows
- Mock providers for isolated testing

## Dependencies

### Internal
- `../providers/` - State management
- `../services/` - Backend communication
- `../widgets/` - Shared UI components
- `../core/theme.dart` - Styling

### External
- `flutter_riverpod` - Provider access
- `go_router` or `Navigator` - Routing

<!-- MANUAL: -->
