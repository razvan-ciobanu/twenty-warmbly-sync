import { defineFrontComponent } from 'twenty-sdk/define';

import { makeSetSyncToWarmbly } from 'src/utils/set-sync-to-warmbly';

export const FRONT_COMPONENT_ID = '08bc9016-bd78-4437-9412-a4079925bac3';

export default defineFrontComponent({
  universalIdentifier: FRONT_COMPONENT_ID,
  name: 'company-sync-on',
  description: 'Set syncToWarmbly=true on the selected companies',
  isHeadless: true,
  component: makeSetSyncToWarmbly('companies', true),
});
