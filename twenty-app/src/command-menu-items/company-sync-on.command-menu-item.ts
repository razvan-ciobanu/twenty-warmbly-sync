import { defineCommandMenuItem, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import { FRONT_COMPONENT_ID } from 'src/front-components/company-sync-on';

export default defineCommandMenuItem({
  universalIdentifier: '888f6c2a-2cee-418e-93df-f6728d798c27',
  label: 'Sync to Warmbly',
  shortLabel: 'Warmbly sync',
  availabilityType: 'RECORD_SELECTION',
  availabilityObjectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
  frontComponentUniversalIdentifier: FRONT_COMPONENT_ID,
});
