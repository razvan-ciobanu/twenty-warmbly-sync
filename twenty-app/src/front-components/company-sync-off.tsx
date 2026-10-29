import { defineFrontComponent } from 'twenty-sdk/define';

import { makeSetSyncToWarmbly } from 'src/utils/set-sync-to-warmbly';

export const FRONT_COMPONENT_ID = 'ee3e0b29-96ba-4e19-90a2-bab3bbdf6c2f';

export default defineFrontComponent({
  universalIdentifier: FRONT_COMPONENT_ID,
  name: 'company-sync-off',
  description: 'Set syncToWarmbly=false on the selected companies',
  isHeadless: true,
  component: makeSetSyncToWarmbly('companies', false),
});
