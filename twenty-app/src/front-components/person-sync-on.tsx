import { defineFrontComponent } from 'twenty-sdk/define';

import { makeSetSyncToWarmbly } from 'src/utils/set-sync-to-warmbly';

export const FRONT_COMPONENT_ID = '4357947c-1ad6-404b-9ce6-ac620e08ebab';

export default defineFrontComponent({
  universalIdentifier: FRONT_COMPONENT_ID,
  name: 'person-sync-on',
  description: 'Set syncToWarmbly=true on the selected people',
  isHeadless: true,
  component: makeSetSyncToWarmbly('people', true),
});
