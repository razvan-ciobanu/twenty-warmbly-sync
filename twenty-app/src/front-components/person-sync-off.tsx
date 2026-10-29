import { defineFrontComponent } from 'twenty-sdk/define';

import { makeSetSyncToWarmbly } from 'src/utils/set-sync-to-warmbly';

export const FRONT_COMPONENT_ID = 'f3f34a74-aee1-4038-b689-d011182ea6f3';

export default defineFrontComponent({
  universalIdentifier: FRONT_COMPONENT_ID,
  name: 'person-sync-off',
  description: 'Set syncToWarmbly=false on the selected people',
  isHeadless: true,
  component: makeSetSyncToWarmbly('people', false),
});
