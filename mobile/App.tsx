import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { StatusBar } from 'expo-status-bar';
import { Text } from 'react-native';

import { colors } from './src/theme';
import InventoryScreen from './src/screens/InventoryScreen';
import ForecastDetailScreen from './src/screens/ForecastDetailScreen';
import VoiceScreen from './src/screens/VoiceScreen';
import AlertsScreen from './src/screens/AlertsScreen';

export type InventoryStackParams = {
  InventoryList: undefined;
  ForecastDetail: { itemId: number; itemName: string };
};

const Tab = createBottomTabNavigator();
const Stack = createNativeStackNavigator<InventoryStackParams>();

function InventoryStack() {
  return (
    <Stack.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: colors.primary },
        headerTintColor: '#fff',
        headerTitleStyle: { fontWeight: '700' },
      }}
    >
      <Stack.Screen name="InventoryList" component={InventoryScreen} options={{ title: 'Inventory' }} />
      <Stack.Screen
        name="ForecastDetail"
        component={ForecastDetailScreen}
        options={({ route }) => ({ title: route.params.itemName })}
      />
    </Stack.Navigator>
  );
}

// Simple emoji tab icons keep us dependency-free (no icon font needed in Expo Go).
function tabIcon(emoji: string) {
  return ({ focused }: { focused: boolean }) => (
    <Text style={{ fontSize: 20, opacity: focused ? 1 : 0.5 }}>{emoji}</Text>
  );
}

export default function App() {
  return (
    <NavigationContainer>
      <StatusBar style="light" />
      <Tab.Navigator
        screenOptions={{
          headerStyle: { backgroundColor: colors.primary },
          headerTintColor: '#fff',
          headerTitleStyle: { fontWeight: '700' },
          tabBarActiveTintColor: colors.primary,
        }}
      >
        <Tab.Screen
          name="Inventory"
          component={InventoryStack}
          options={{ headerShown: false, tabBarIcon: tabIcon('📦') }}
        />
        <Tab.Screen
          name="Add by Voice"
          component={VoiceScreen}
          options={{ tabBarIcon: tabIcon('🎤') }}
        />
        <Tab.Screen name="Alerts" component={AlertsScreen} options={{ tabBarIcon: tabIcon('🔔') }} />
      </Tab.Navigator>
    </NavigationContainer>
  );
}
