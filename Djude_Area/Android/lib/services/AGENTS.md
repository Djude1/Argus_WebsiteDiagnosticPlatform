<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-16 | Updated: 2026-03-16 -->

# services

## Purpose
Service layer handling all external communication and device hardware access. Provides abstraction between UI and backend/data sources.

## Key Files
| File | Description |
|------|-------------|
| `api_service.dart` | REST API client for HTTP requests |
| `websocket_service.dart` | WebSocket connection management for real-time data |
| `audio_service.dart` | Audio recording, playback, and streaming |
| `camera_service.dart` | Camera capture and frame streaming |
| `auth_service.dart` | Authentication token management |
| `contacts_service.dart` | Emergency contacts CRUD operations |
| `discovery_service.dart` | Server discovery on local network |
| `imu_service.dart` | IMU sensor data collection |

## For AI Agents

### Working In This Directory
- Services should be singletons or provided via Riverpod
- All async operations return Future<T>
- Handle errors gracefully with try-catch
- Log important events for debugging

### Common Patterns
```dart
class MyService {
  Future<Result> fetchData() async {
    try {
      final response = await _client.get('/endpoint');
      return Result.fromJson(response.data);
    } catch (e) {
      logger.e('Failed to fetch data: $e');
      rethrow;
    }
  }
}
```

### Testing Requirements
- Unit test each service method
- Mock HTTP/WebSocket clients
- Test error handling paths

## Dependencies

### Internal
- `../core/constants.dart` - API endpoints and config
- `../providers/` - State updates

### External
- `http` or `dio` - HTTP client
- `web_socket_channel` - WebSocket
- `camera` - Camera access
- `record` - Audio recording
- `audioplayers` - Audio playback
- `sensors_plus` - IMU sensors

<!-- MANUAL: -->
