import { useEffect } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { registerForPushNotificationsAsync } from "../services/notifications";
import { SHOP_ID_KEY } from "../services/api";

export default function RootLayout() {
  useEffect(() => {
    AsyncStorage.getItem(SHOP_ID_KEY).then((shopId) => {
      if (shopId) registerForPushNotificationsAsync(shopId).catch(() => {});
    });
  }, []);

  return (
    <>
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerShown: false }} />
    </>
  );
}
