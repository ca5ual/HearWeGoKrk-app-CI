// 5.8 Trip in progress. Updated by the backend's trip monitor (`ui` trip_live every ~10 s).
import React from "react";
import { ScrollView } from "react-native";

import { useAgent } from "@/agent/AgentContext";
import { TripView } from "@/components/route";
import { T } from "@/components/ui";
import { space } from "@/theme";
import type { RideLeg } from "@/types";

export default function Trip() {
  const { trip, ui } = useAgent();
  // Where to get off: the last ride leg of the planned route, if it uses this line.
  const r = ui.route_results;
  const lastRide = r?.status === "ok" ? (r.best.legs.filter((l) => l.type === "ride") as RideLeg[]).at(-1) : undefined;
  const target = lastRide && trip && lastRide.line_number === trip.line_number ? lastRide.to : null;

  return (
    <ScrollView contentContainerStyle={{ padding: space(4), gap: space(4) }}>
      {trip ? <TripView trip={trip} target={target} /> : <T variant="muted">Nie jesteś teraz w pojeździe.</T>}
    </ScrollView>
  );
}
