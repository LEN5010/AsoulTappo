<script setup lang="ts">
// Someone else's profile, read only. A room partner's comes from the room server, a board row's from the board.
// The own profile is the 排行 page, which shows the same card editable.
import { computed, ref } from "vue";
import { getCard, type ManifestCard } from "../manifest";
import type { BoardRow } from "../net/api";
import type { Member, MemberProfile } from "../net/protocol";
import { loadBoardProfile } from "../stores/player";
import { loadProfile, members, shownNick } from "../stores/room";
import { settings } from "../stores/settings";
import { getPlate } from "../pet/plates";
import Modal from "../ui/Modal.vue";
import CardDetail from "./CardDetail.vue";
import ProfileCard from "./ProfileCard.vue";

/** `id` is a room partner's member id; `row` a save on the collection board. */
const props = defineProps<{ id?: string; row?: BoardRow }>();
const emit = defineEmits<{ close: [] }>();

// A partner who leaves stays on screen as last seen until the profile closes.
const found = props.id ? members.get(props.id) : undefined;
let last: Member | null = found ? { ...found } : null;
const partner = computed(() => {
  const now = props.id ? members.get(props.id) : undefined;
  if (now) last = { ...now };
  return last;
});
const who = computed(() => props.row ?? partner.value);
if (!who.value) emit("close");

const name = computed(() => (who.value ? shownNick(who.value) : ""));
/** The plate on the banner, only while partners' plates are shown. */
const plate = computed(() => (settings.showPlates ? getPlate(who.value?.plate) : null));

/** Undefined while it loads, null when the server did not answer. */
const remote = ref<MemberProfile | null | undefined>(undefined);
void (props.row ? loadBoardProfile(props.row.id) : props.id ? loadProfile(props.id) : Promise.resolve(null))
  .then((p) => { remote.value = p; });
const showcase = computed(() =>
  (remote.value?.showcase ?? []).map((id) => getCard(id)).filter((c): c is ManifestCard => !!c));
const progress = computed(() => (remote.value === undefined ? undefined : remote.value?.progress ?? null));

/** A card opened from the profile, as a preview: this save may not own it. */
const viewing = ref<ManifestCard | null>(null);
</script>

<template>
  <CardDetail v-if="viewing" :card="viewing" preview @close="viewing = null" />
  <Modal v-else :title="`${name}的主页`" wide @close="emit('close')">
    <ProfileCard
      :plate="plate" :name="name" :character="who?.character ?? ''" :showcase="showcase" :progress="progress"
      :failed="remote === null" @open="viewing = $event"
    />
  </Modal>
</template>
