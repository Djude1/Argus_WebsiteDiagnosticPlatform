<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-16 | Updated: 2026-03-16 -->

# admin

## Purpose
Administrative screens for user management and system configuration. Only accessible to users with admin privileges.

## Key Files
| File | Description |
|------|-------------|
| `admin_screen.dart` | Main admin dashboard |
| `user_manage_screen.dart` | User account management interface |

## For AI Agents

### Working In This Directory
- All screens require admin authentication
- Use `auth_provider.dart` to verify admin status
- Redirect non-admin users to login

### Common Patterns
- Admin-only widgets with role-based access control
- DataTable for listing users
- CRUD operations via `auth_service.dart`

## Dependencies

### Internal
- `../../providers/auth_provider.dart` - Auth state
- `../../services/auth_service.dart` - User management API

<!-- MANUAL: -->
