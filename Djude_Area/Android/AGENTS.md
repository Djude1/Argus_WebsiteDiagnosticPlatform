<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-16 | Updated: 2026-03-16 -->

# Android

## Purpose
Flutter-based Android companion application for the AI navigation glasses system. Provides real-time camera streaming, voice chat, AR navigation display, and administrative functions.

## Key Files
| File | Description |
|------|-------------|
| `lib/main.dart` | Application entry point and initialization |
| `lib/app.dart` | Root app widget with routing configuration |
| `lib/core/constants.dart` | App-wide constants including API endpoints |
| `lib/core/theme.dart` | Material theme configuration |
| `pubspec.yaml` | Flutter dependencies and project configuration |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `lib/screens/` | UI screens and pages (see `lib/screens/AGENTS.md`) |
| `lib/services/` | Backend service integrations (see `lib/services/AGENTS.md`) |
| `lib/providers/` | State management providers |
| `lib/widgets/` | Reusable UI components |
| `lib/core/` | Core utilities and constants |
| `android/` | Native Android project configuration |

## For AI Agents

### Working In This Directory
- Flutter SDK 3.0+ required
- Use `flutter pub get` to install dependencies
- Build with `flutter build apk` for release
- Run with `flutter run` for development

### Testing Requirements
- Unit tests in `test/` directory
- Integration tests in `integration_test/`
- Run `flutter test` before committing

### Common Patterns
- Provider pattern for state management
- Service layer for API communication
- Screen widgets for UI pages
- Reusable widgets in `widgets/` directory

## Dependencies

### Internal
- Connects to FastAPI backend via WebSocket
- Uses `lib/services/websocket_service.dart` for real-time communication

### External
- `flutter_riverpod` - State management
- `web_socket_channel` - WebSocket communication
- `camera` - Camera access and streaming
- `google_maps_flutter` - Map display
- `arcore_flutter_plugin` - AR functionality
- `permission_handler` - Runtime permissions
- `shared_preferences` - Local storage
- `provider` - State management

<!-- MANUAL: -->
