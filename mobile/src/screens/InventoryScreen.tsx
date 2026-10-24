import { useCallback, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';

import type { InventoryStackParams } from '../../App';
import { api, type Item } from '../api';
import { Loading, ErrorBox } from '../components';
import { colors } from '../theme';

type Props = NativeStackScreenProps<InventoryStackParams, 'InventoryList'>;

export default function InventoryScreen({ navigation }: Props) {
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const data = await api.getItems();
      setItems(data);
    } catch (e: any) {
      setError(e.message ?? 'Failed to load items');
    } finally {
      setLoading(false);
    }
  }, []);

  // Reload each time the tab/screen regains focus (e.g. after a voice update).
  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  if (loading) return <Loading label="Loading inventory…" />;
  if (error) return <ErrorBox message={error} onRetry={load} />;

  return (
    <FlatList
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: 12 }}
      data={items}
      keyExtractor={(i) => String(i.id)}
      refreshControl={<RefreshControl refreshing={false} onRefresh={load} />}
      ListEmptyComponent={<Text style={styles.empty}>No items yet.</Text>}
      renderItem={({ item }) => (
        <Pressable
          style={styles.card}
          onPress={() => navigation.navigate('ForecastDetail', { itemId: item.id, itemName: item.name })}
        >
          <View style={{ flex: 1 }}>
            <Text style={styles.name}>{item.name}</Text>
            <Text style={styles.sub}>
              Stock: {item.current_stock} {item.unit} · Reorder at {item.reorder_level}
            </Text>
          </View>
          {item.low_stock && (
            <View style={styles.badge}>
              <Text style={styles.badgeText}>LOW</Text>
            </View>
          )}
          <Text style={styles.chevron}>›</Text>
        </Pressable>
      )}
    />
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.card,
    padding: 16,
    borderRadius: 12,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: colors.border,
  },
  name: { fontSize: 17, fontWeight: '700', color: colors.text },
  sub: { marginTop: 4, color: colors.subtext, fontSize: 13 },
  badge: { backgroundColor: colors.danger, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3, marginRight: 8 },
  badgeText: { color: '#fff', fontWeight: '800', fontSize: 11 },
  chevron: { fontSize: 24, color: colors.subtext },
  empty: { textAlign: 'center', marginTop: 40, color: colors.subtext },
});
