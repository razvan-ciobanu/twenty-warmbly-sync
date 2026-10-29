import { defineCommandMenuItem, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import { FRONT_COMPONENT_ID } from 'src/front-components/person-sync-off';

export default defineCommandMenuItem({
  universalIdentifier: '81e9f936-41ec-446f-ac60-3a73f2b718a9',
  label: 'Stop syncing to Warmbly',
  shortLabel: 'Stop Warmbly sync',
  availabilityType: 'RECORD_SELECTION',
  availabilityObjectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.person.universalIdentifier,
  frontComponentUniversalIdentifier: FRONT_COMPONENT_ID,
});
