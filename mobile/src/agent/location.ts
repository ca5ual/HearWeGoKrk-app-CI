import * as Location from "expo-location";

export type Coords = { lat: number; lon: number };

/** Watch the phone's GPS. Returns an unsubscribe function. If permission is denied, nothing is sent
 *  and the backend falls back to the venue (or the stage override from POST /demo/gps). */
export async function watchLocation(onFix: (c: Coords) => void): Promise<() => void> {
  const { granted } = await Location.requestForegroundPermissionsAsync();
  if (!granted) return () => {};
  const sub = await Location.watchPositionAsync(
    { accuracy: Location.Accuracy.High, timeInterval: 5000, distanceInterval: 10 },
    (loc) => onFix({ lat: loc.coords.latitude, lon: loc.coords.longitude }),
  );
  return () => sub.remove();
}
