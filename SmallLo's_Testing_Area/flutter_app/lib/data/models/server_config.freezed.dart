// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'server_config.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

T _$identity<T>(T value) => value;

final _privateConstructorUsedError = UnsupportedError(
  'It seems like you constructed your class using `MyClass._()`. This constructor is only meant to be used by freezed and you are not supposed to need it nor use it.\nPlease check the documentation here for more information: https://github.com/rrousselGit/freezed#adding-getters-and-methods-to-our-models',
);

/// @nodoc
mixin _$ServerConfig {
  String get serverIp => throw _privateConstructorUsedError;
  int get serverPort => throw _privateConstructorUsedError;
  bool get autoConnect => throw _privateConstructorUsedError;

  /// Create a copy of ServerConfig
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  $ServerConfigCopyWith<ServerConfig> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $ServerConfigCopyWith<$Res> {
  factory $ServerConfigCopyWith(
    ServerConfig value,
    $Res Function(ServerConfig) then,
  ) = _$ServerConfigCopyWithImpl<$Res, ServerConfig>;
  @useResult
  $Res call({String serverIp, int serverPort, bool autoConnect});
}

/// @nodoc
class _$ServerConfigCopyWithImpl<$Res, $Val extends ServerConfig>
    implements $ServerConfigCopyWith<$Res> {
  _$ServerConfigCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  /// Create a copy of ServerConfig
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? serverIp = null,
    Object? serverPort = null,
    Object? autoConnect = null,
  }) {
    return _then(
      _value.copyWith(
            serverIp: null == serverIp
                ? _value.serverIp
                : serverIp // ignore: cast_nullable_to_non_nullable
                      as String,
            serverPort: null == serverPort
                ? _value.serverPort
                : serverPort // ignore: cast_nullable_to_non_nullable
                      as int,
            autoConnect: null == autoConnect
                ? _value.autoConnect
                : autoConnect // ignore: cast_nullable_to_non_nullable
                      as bool,
          )
          as $Val,
    );
  }
}

/// @nodoc
abstract class _$$ServerConfigImplCopyWith<$Res>
    implements $ServerConfigCopyWith<$Res> {
  factory _$$ServerConfigImplCopyWith(
    _$ServerConfigImpl value,
    $Res Function(_$ServerConfigImpl) then,
  ) = __$$ServerConfigImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({String serverIp, int serverPort, bool autoConnect});
}

/// @nodoc
class __$$ServerConfigImplCopyWithImpl<$Res>
    extends _$ServerConfigCopyWithImpl<$Res, _$ServerConfigImpl>
    implements _$$ServerConfigImplCopyWith<$Res> {
  __$$ServerConfigImplCopyWithImpl(
    _$ServerConfigImpl _value,
    $Res Function(_$ServerConfigImpl) _then,
  ) : super(_value, _then);

  /// Create a copy of ServerConfig
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? serverIp = null,
    Object? serverPort = null,
    Object? autoConnect = null,
  }) {
    return _then(
      _$ServerConfigImpl(
        serverIp: null == serverIp
            ? _value.serverIp
            : serverIp // ignore: cast_nullable_to_non_nullable
                  as String,
        serverPort: null == serverPort
            ? _value.serverPort
            : serverPort // ignore: cast_nullable_to_non_nullable
                  as int,
        autoConnect: null == autoConnect
            ? _value.autoConnect
            : autoConnect // ignore: cast_nullable_to_non_nullable
                  as bool,
      ),
    );
  }
}

/// @nodoc

class _$ServerConfigImpl implements _ServerConfig {
  const _$ServerConfigImpl({
    this.serverIp = '192.168.1.100',
    this.serverPort = 8081,
    this.autoConnect = false,
  });

  @override
  @JsonKey()
  final String serverIp;
  @override
  @JsonKey()
  final int serverPort;
  @override
  @JsonKey()
  final bool autoConnect;

  @override
  String toString() {
    return 'ServerConfig(serverIp: $serverIp, serverPort: $serverPort, autoConnect: $autoConnect)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$ServerConfigImpl &&
            (identical(other.serverIp, serverIp) ||
                other.serverIp == serverIp) &&
            (identical(other.serverPort, serverPort) ||
                other.serverPort == serverPort) &&
            (identical(other.autoConnect, autoConnect) ||
                other.autoConnect == autoConnect));
  }

  @override
  int get hashCode =>
      Object.hash(runtimeType, serverIp, serverPort, autoConnect);

  /// Create a copy of ServerConfig
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  @pragma('vm:prefer-inline')
  _$$ServerConfigImplCopyWith<_$ServerConfigImpl> get copyWith =>
      __$$ServerConfigImplCopyWithImpl<_$ServerConfigImpl>(this, _$identity);
}

abstract class _ServerConfig implements ServerConfig {
  const factory _ServerConfig({
    final String serverIp,
    final int serverPort,
    final bool autoConnect,
  }) = _$ServerConfigImpl;

  @override
  String get serverIp;
  @override
  int get serverPort;
  @override
  bool get autoConnect;

  /// Create a copy of ServerConfig
  /// with the given fields replaced by the non-null parameter values.
  @override
  @JsonKey(includeFromJson: false, includeToJson: false)
  _$$ServerConfigImplCopyWith<_$ServerConfigImpl> get copyWith =>
      throw _privateConstructorUsedError;
}
