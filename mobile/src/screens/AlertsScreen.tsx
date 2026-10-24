import { useCallback, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import { FlatList, RefreshControl, StyleSheet, Text, View } from 'react-native';

import { api, type Alert } from '../api';
import { Button, ErrorBox, Loading } from '../components';
import { colors } from '../theme';

export default function AlertsScreen() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      setAlerts(await api.getAlerts());
    } catch (e: any) {
      setError(e.message ?? 'Failed to load alerts');
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const runCheck = async () => {
    try {
      setRunning(true);
      setBanner(null);
      setError(null);
      const res = await api.runAlertCheck();
      setBanner(`Check complete — ${res.created} new alert(s).`);
      await load();
    } catch (e: any) {
      setError(e.message ?? 'Alert check failed');
    } finally {
      setRunning(false);
    }
  };

  const giveFeedback = async (id: number, useful: boolean) => {
    try {
      const updated = await api.setAlertFeedback(id, useful);
      setAlerts((prev) => prev.map((a) => (a.id === id ? updated : a)));
    } catch (e: any) {
      setError(e.message ?? 'Could not save feedback');
    }
  };

  if (loading) return <Loading label="Loading alerts…" />;

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <View style={styles.header}>
        <Button title={running ? 'Checking…' : '🔄 Run check now'} onPress={runCheck} disabled={running} />
        {banner && <Text style={styles.banner}>{banner}</Text>}
      </View>
      {error && <ErrorBox message={error} onRetry={load} />}
      <FlatList
        contentContainerStyle={{ padding: 12 }}
        data={alerts}
        keyExtractor={(a) => String(a.id)}
        refreshControl={<RefreshControl refreshing={false} onRefresh={load} />}
        ListEmptyComponent={
          <Text style={styles.empty}>No alerts yet. Tap “Run check now”.</Text>
        }
        renderItem={({ item }) => (
          <View style={styles.card}>
            <Text style={styles.message}>{item.message}</Text>
            <Text style={styles.time}>{new Date(item.created_at).toLocaleString()}</Text>
            <View style={styles.feedbackRow}>
              <Text style={styles.feedbackLabel}>Was this useful?</Text>
              <FeedbackButton
                label="👍 Useful"
                active={item.useful === true}
                onPress={() => giveFeedback(item.id, true)}
              />
              <FeedbackButton
                label="👎 Not useful"
                active={item.useful === false}
                onPress={() => giveFeedback(item.id, false)}
              />
            </View>
          </View>
        )}
      />
    </View>
  );
}

function FeedbackButton({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <Text onPress={onPress} style={[styles.feedbackBtn, active && styles.feedbackBtnActive]}>
      {label}
    </Text>
  );
}

const styles = StyleSheet.create({
  header: { padding: 12, gap: 8, borderBottomWidth: 1, borderColor: colors.border, backgroundColor: colors.card },
  banner: { color: colors.primaryDark, fontWeight: '600' },
  card: { backgroundColor: colors.card, borderRadius: 12, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: colors.border },
  message: { fontSize: 15, color: colors.text, fontWeight: '600' },
  time: { fontSize: 12, color: colors.subtext, marginTop: 4 },
  feedbackRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 12, flexWrap: 'wrap' },
  feedbackLabel: { color: colors.subtext, fontSize: 13 },
  feedbackBtn: { paddingVertical: 6, paddingHorizontal: 10, borderRadius: 8, borderWidth: 1, borderColor: colors.border, overflow: 'hidden', color: colors.text },
  feedbackBtnActive: { backgroundColor: colors.primary, color: '#fff', borderColor: colors.primary },
  empty: { textAlign: 'center', marginTop: 40, color: colors.subtext },
});
