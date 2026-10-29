import { defineCommandMenuItem, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import { FRONT_COMPONENT_ID } from 'src/front-components/person-sync-on';

export default defineCommandMenuItem({
  universalIdentifier: '8f6bffcf-1d09-4aae-aa7a-362d1de43039',
  label: 'Sync to Warmbly',
  shortLabel: 'Warmbly sync',
  availabilityType: 'RECORD_SELECTION',
  availabilityObjectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.person.universalIdentifier,
  frontComponentUniversalIdentifier: FRONT_COMPONENT_ID,
});
