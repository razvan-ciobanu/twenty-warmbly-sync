import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

export default defineField({
  universalIdentifier: 'a302492e-5d6b-40b8-b907-94cbc2ce3672',
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
  name: 'doNotContact',
  type: FieldType.BOOLEAN,
  label: 'Do not contact',
  description: 'Opted out of outreach; kept in sync with the Warmbly suppression list',
  icon: 'IconMailOff',
  defaultValue: false,
});
