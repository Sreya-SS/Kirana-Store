/** Small shared UI pieces: loading, error, and a primary button. */
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { colors } from './theme';

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <View style={styles.center}>
      <ActivityIndicator size="large" color={colors.primary} />
      <Text style={styles.muted}>{label}</Text>
    </View>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <View style={styles.errorBox}>
      <Text style={styles.errorText}>⚠️ {message}</Text>
      {onRetry && (
        <Button title="Retry" onPress={onRetry} variant="danger" />
      )}
    </View>
  );
}

export function Button({
  title,
  onPress,
  variant = 'primary',
  disabled = false,
}: {
  title: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'danger';
  disabled?: boolean;
}) {
  const bg =
    variant === 'primary' ? colors.primary : variant === 'danger' ? colors.danger : '#e8eceb';
  const fg = variant === 'secondary' ? colors.text : '#fff';
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: bg, opacity: disabled ? 0.5 : pressed ? 0.85 : 1 },
      ]}
    >
      <Text style={[styles.buttonText, { color: fg }]}>{title}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 },
  muted: { marginTop: 12, color: colors.subtext },
  errorBox: { margin: 16, padding: 16, backgroundColor: '#fdecec', borderRadius: 12, gap: 12 },
  errorText: { color: colors.danger, fontSize: 15 },
  button: { paddingVertical: 12, paddingHorizontal: 18, borderRadius: 10, alignItems: 'center' },
  buttonText: { fontSize: 15, fontWeight: '700' },
});
