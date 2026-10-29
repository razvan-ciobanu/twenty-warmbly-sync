import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

export default defineField({
  universalIdentifier: 'd00b3293-6022-4513-9ceb-a5d4a9f19427',
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.person.universalIdentifier,
  name: 'doNotContact',
  type: FieldType.BOOLEAN,
  label: 'Do not contact',
  description: 'Opted out of outreach; kept in sync with the Warmbly suppression list',
  icon: 'IconMailOff',
  defaultValue: false,
});
